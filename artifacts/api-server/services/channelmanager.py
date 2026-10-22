"""Safe Decimal calculations and bounded, explicit CSV adapters."""
import csv
import io
from decimal import Decimal, DecimalException, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_DOWN, ROUND_UP
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

D = Decimal
Money = str


def number(value):
    text = str(value)
    if len(text) > 64:
        raise ValueError("Numeric cell exceeds 64 characters")
    try:
        result = D(text)
    except DecimalException as exc:
        raise ValueError("Invalid decimal number") from exc
    if (not result.is_finite() or abs(result) > D("1000000000000") or
            result.as_tuple().exponent < -12 or result.as_tuple().exponent > 12):
        raise ValueError("Number must be finite, at most 1e12, and have at most 12 decimal places")
    return result


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rule(Strict):
    kind: Literal["fixed", "percentage"]
    value: str

    @model_validator(mode="after")
    def valid(self):
        number(self.value)
        return self


class Semantics(Strict):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    price_basis: Literal["net", "gross"]
    vat_rate: str

    @model_validator(mode="after")
    def valid_vat(self):
        if not 0 <= number(self.vat_rate) <= 1:
            raise ValueError("VAT must be an explicit fraction between 0 and 1")
        return self


class ChannelConfig(Semantics):
    rule: Rule
    category_overrides: dict[str, Rule] = Field(default_factory=dict, max_length=500)
    sku_overrides: dict[str, Rule] = Field(default_factory=dict, max_length=5000)
    precision: int = Field(default=2, ge=0, le=4)
    increment: str = "0.01"
    rounding: Literal["HALF_UP", "HALF_EVEN", "DOWN", "UP"] = "HALF_UP"
    min_price: str | None = None
    min_margin: str | None = None
    max_change_absolute: str | None = None
    max_change_percent: str | None = None
    readback_tolerance: str = "0"
    export_columns: dict[str, Literal["sku", "name", "category", "target_price"]] = Field(
        default_factory=lambda: {"sku": "sku", "price": "target_price"}, min_length=2, max_length=10)
    delimiter: Literal[",", ";", "\t", "|"] = ";"
    decimal: Literal[".", ","] = "."
    schedule_enabled: bool = False
    schedule_source_shop_id: int | None = Field(default=None, gt=0)
    schedule_hour_utc: int = Field(default=2, ge=0, le=23)

    @model_validator(mode="after")
    def valid_config(self):
        for key in ("increment", "min_price", "min_margin", "max_change_absolute",
                    "max_change_percent", "readback_tolerance"):
            value = getattr(self, key)
            if value is not None and number(value) < 0:
                raise ValueError(f"{key} cannot be negative")
        step = number(self.increment)
        if step <= 0 or step % D(10) ** -self.precision:
            raise ValueError("Increment must be positive and representable at precision")
        if self.min_margin is not None and number(self.min_margin) >= 1:
            raise ValueError("Minimum margin must be below 1")
        if not {"sku", "target_price"} <= set(self.export_columns.values()):
            raise ValueError("Export requires sku and target_price")
        if any(not k or len(k) > 100 or k.lstrip().startswith(("=", "+", "-", "@")) for k in self.export_columns):
            raise ValueError("Invalid export header")
        return self


class InputRow(Strict):
    sku: str = Field(min_length=1, max_length=500)
    name: str = Field(default="", max_length=500)
    category: str = Field(default="", max_length=500)
    base_price: str
    cost: str | None = None
    current_price: str | None = None

    @model_validator(mode="after")
    def valid_row(self):
        if not self.sku.strip():
            raise ValueError("SKU required")
        for key in ("base_price", "cost", "current_price"):
            value = getattr(self, key)
            if value is not None and number(value) < 0:
                raise ValueError(f"{key} cannot be negative")
        return self


class BasisInput(Semantics):
    cost_basis: Literal["net"]
    provenance: Literal["manual_csv", "PriceShape_unverified"]
    notes: str = Field(min_length=1, max_length=2000)
    rows: list[InputRow] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def unique(self):
        if len({r.sku for r in self.rows}) != len(self.rows):
            raise ValueError("Duplicate SKU")
        return self


class CSVSettings(Strict):
    mapping: dict[str, str] = Field(min_length=2, max_length=6)
    delimiter: Literal[",", ";", "\t", "|"] = ";"
    decimal: Literal[".", ","] = "."


def parse_csv(data, settings):
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("CSV exceeds 2 MiB")
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=settings.delimiter)
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)) or not set(settings.mapping.values()) <= set(headers):
        raise ValueError("Duplicate or missing mapped CSV headers")
    rows = []
    for raw in reader:
        if len(rows) >= 5000 or None in raw or any(v is None or len(v) > 500 for v in raw.values()):
            raise ValueError("CSV exceeds row/cell bounds or has malformed rows")
        row = {}
        for key, header in settings.mapping.items():
            value = raw[header]
            if key in ("base_price", "cost", "current_price", "actual_price"):
                if settings.decimal == "," and "." in value:
                    raise ValueError("Thousands separators / mismatched decimal not supported")
                value = value.replace(settings.decimal, ".")
                value = str(number(value)) if value else None
            row[key] = value
        rows.append(row)
    if not rows:
        raise ValueError("CSV contains no rows")
    return rows


def calculate(basis, config):
    c = ChannelConfig.model_validate(config)
    if basis["currency"] != c.currency:
        raise ValueError("Currency mismatch; FX conversion is not supported")
    results = []
    mode = {"HALF_UP": ROUND_HALF_UP, "HALF_EVEN": ROUND_HALF_EVEN, "DOWN": ROUND_DOWN, "UP": ROUND_UP}[c.rounding]
    for row in basis["rows"]:
        errors = []
        source = "sku" if row["sku"] in c.sku_overrides else "category" if row["category"] in c.category_overrides else "shop"
        rule = c.sku_overrides.get(row["sku"], c.category_overrides.get(row["category"], c.rule))
        base_net = number(row["base_price"]) / (1 + number(basis["vat_rate"]) if basis["price_basis"] == "gross" else 1)
        base = base_net * (1 + number(c.vat_rate) if c.price_basis == "gross" else 1)
        target = base + number(rule.value) if rule.kind == "fixed" else base * (1 + number(rule.value) / 100)
        if abs(target) > D("1000000000000"):
            results.append({**row, "rule_source": source, "rule": rule.model_dump(),
                            "target_price": None, "current_delta": None, "net_margin": None,
                            "errors": ["Calculated target exceeds supported 1e12 bound"]})
            continue
        target = ((target / number(c.increment)).quantize(D(1), rounding=mode) * number(c.increment)).quantize(D(10) ** -c.precision, rounding=mode)
        net = target / (1 + number(c.vat_rate) if c.price_basis == "gross" else 1)
        margin = (net - number(row["cost"])) / net if row["cost"] is not None and net > 0 else None
        if target <= 0:
            errors.append("Target must be positive")
        if c.min_price is not None and target < number(c.min_price):
            errors.append("Below minimum price")
        if c.min_margin is not None and (margin is None or margin < number(c.min_margin)):
            errors.append("Missing cost or below minimum net margin")
        current = row["current_price"]
        # Current price is declared in basis semantics; convert to destination basis.
        current = (number(current) / (1 + number(basis["vat_rate"]) if basis["price_basis"] == "gross" else 1)
                   * (1 + number(c.vat_rate) if c.price_basis == "gross" else 1)) if current is not None else None
        delta = target - current if current is not None else None
        if c.max_change_absolute is not None and (delta is None or abs(delta) > number(c.max_change_absolute)):
            errors.append("Missing current price or absolute change guard exceeded")
        if c.max_change_percent is not None and (current is None or current == 0 or abs(delta / current * 100) > number(c.max_change_percent)):
            errors.append("Missing/zero current price or percentage change guard exceeded")
        results.append({**row, "rule_source": source, "rule": rule.model_dump(), "target_price": str(target),
                        "current_delta": str(delta) if delta is not None else None,
                        "net_margin": str(margin) if margin is not None else None, "errors": errors})
    return results


def export_csv(rows, config):
    c = ChannelConfig.model_validate(config)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=c.delimiter, lineterminator="\r\n")
    writer.writerow(c.export_columns.keys())
    for row in rows:
        values = []
        for key in c.export_columns.values():
            value = row.get(key, "")
            if key == "target_price":
                value = value.replace(".", c.decimal)
            elif value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return stream.getvalue()
