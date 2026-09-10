"""Genereer het vaste v1 Excel-template voor concurrentprofielverrijking."""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo


SCHEMA_VERSION = "competitor_profile_v1"
OUTPUT = Path(__file__).resolve().parents[1] / "templates" / "concurrentprofiel_template_v1.xlsx"

SHEETS = {
    "Bedrijven": [
        "schema_version", "company_key", "company_name", "field_key", "value_text",
        "value_number", "value_boolean", "value_date", "value_currency",
        "value_unit", "status", "information_layer", "confidence", "as_of_date",
        "source_id", "source_origin", "overwrite_policy", "notes",
    ],
    "Relaties_Lidmaatschappen": [
        "schema_version", "relation_key", "company_key", "relation_class",
        "relation_type", "direction", "related_entity_name", "related_entity_key",
        "related_country", "role", "relation_status", "information_layer",
        "confidence", "as_of_date", "valid_from", "valid_to", "geographic_scope",
        "central_purchasing", "source_id", "notes",
    ],
    "Bronnen": [
        "schema_version", "source_id", "company_key", "source_type", "source_title",
        "publisher", "source_url", "publication_date", "accessed_date",
        "reliability", "supports_claim", "notes",
    ],
}

CHOICES = {
    "status": ["known", "unknown", "blocked", "needs_review"],
    "information_layer": ["feit", "schatting", "afgeleid_signaal", "hypothese"],
    "source_origin": ["creditsafe", "openbare_bron", "handmatig"],
    "overwrite_policy": ["locked_context", "only_stronger_source", "enrichable"],
    "relation_class": ["juridisch", "commercieel"],
    "relation_type": [
        "parent", "ultimate_parent", "subsidiary", "sister", "quantore",
        "inkooporganisatie", "cooperatie", "franchise_formule", "keten",
        "dealer_retailnetwerk", "brancheverband",
    ],
    "direction": ["outgoing", "incoming", "mutual"],
    "relation_status": ["known", "unknown", "blocked", "needs_review"],
    "central_purchasing": ["yes", "no", "unknown"],
    "source_type": [
        "creditsafe", "kvk", "jaarrekening", "jaarverslag", "bedrijfswebsite",
        "netwerkwebsite", "brancheorganisatie", "persbericht", "nieuwsartikel",
        "linkedin", "social_media", "externe_schatting", "handmatig",
    ],
    "reliability": ["hoog", "middel", "laag"],
    "supports_claim": ["yes", "no", "partial"],
}

FIELD_CATALOG = [
    ("legal_name", "text", "Creditsafe", "Juridische naam"),
    ("kvk_number", "text", "Creditsafe", "KvK-nummer"),
    ("creditsafe_id", "text", "Creditsafe", "Creditsafe-identificatie"),
    ("creditsafe_status", "text", "Creditsafe", "Bedrijfsstatus uit Creditsafe"),
    ("founded_year", "integer", "Verrijking", "Oprichtingsjaar"),
    ("customer_model", "enum:b2c|b2b|hybrid|unknown", "Verrijking", "Klantmodel"),
    ("size_class", "enum:micro|klein|middelgroot|groot|enterprise|unknown", "Verrijking", "Omvang"),
    ("employee_range_min", "integer", "Verrijking", "Minimum medewerkers"),
    ("employee_range_max", "integer", "Verrijking", "Maximum medewerkers"),
    ("revenue_range_min", "decimal", "Verrijking", "Minimum omzet"),
    ("revenue_range_max", "decimal", "Verrijking", "Maximum omzet"),
    ("geographic_scale", "enum:lokaal|nationaal|eu|globaal|unknown", "Verrijking", "Geografische schaal"),
    ("ownership_type", "text", "Verrijking", "Eigendomstype; geen lidmaatschap"),
    ("headquarters_country", "iso_country_2", "Verrijking", "Land hoofdkantoor"),
    ("inventory_model", "enum:eigen_voorraad|dropship|hybride|unknown", "Verrijking", "Voorraadmodel"),
    ("warehouse_count", "integer", "Verrijking", "Aantal magazijnen"),
    ("warehouse_locations", "text", "Verrijking", "Plaatsen/landen, puntkomma-gescheiden"),
    ("dropship_share_pct", "decimal_0_100", "Verrijking", "Dropshipaandeel"),
    ("own_stock_share_pct", "decimal_0_100", "Verrijking", "Eigen-voorraadaandeel"),
    ("next_day_delivery", "boolean", "Verrijking", "Volgende-dag-levering"),
    ("same_day_delivery", "boolean", "Verrijking", "Zelfde-dag-levering"),
    ("marketplace_role", "enum:geen|verkoper|platform|beide|unknown", "Verrijking", "Marktplaatsrol"),
]


def style_table(ws, table_name: str, widths: dict[str, int] | None = None) -> None:
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    table = Table(displayName=table_name, ref=ws.dimensions)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
        showRowStripes=True, showColumnStripes=False,
    )
    ws.add_table(table)
    ws.row_dimensions[1].height = 30
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for idx, cell in enumerate(ws[1], 1):
        width = (widths or {}).get(str(cell.value), 16)
        ws.column_dimensions[get_column_letter(idx)].width = width


def add_choice(ws, column_name: str, values: list[str], max_row: int = 1000) -> None:
    column = [cell.value for cell in ws[1]].index(column_name) + 1
    formula = '"' + ",".join(values) + '"'
    dv = DataValidation(type="list", formula1=formula, allow_blank=False)
    dv.error = "Kies een waarde uit de vaste v1-keuzelijst."
    dv.errorTitle = "Ongeldige waarde"
    dv.prompt = "Technische v1-waarde; niet vertalen of wijzigen."
    dv.promptTitle = column_name
    dv.showErrorMessage = True
    dv.showInputMessage = True
    ws.add_data_validation(dv)
    dv.add(f"{get_column_letter(column)}2:{get_column_letter(column)}{max_row}")


def build_instructions(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "Instructies"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 110
    rows = [
        ("Template", "Concurrentprofiel verrijking"),
        ("schema_version", SCHEMA_VERSION),
        ("Doel", "Creditsafe-basiscontext en concurrentnamen aanbieden voor controleerbare openbare verrijking."),
        ("Vaste structuur", "Wijzig geen bladnamen, technische kolomnamen, company_key, relation_key, source_id of schema_version."),
        ("Onbekend", "Gebruik status=unknown en laat alle value_* cellen leeg. Leeg zonder expliciete status is niet toegestaan."),
        ("Waarde-opslag", "Vul per Bedrijven-rij precies één passend value_* veld. Percentages staan als 0–100 in value_number."),
        ("Bronbeleid", "Creditsafe-rijen hebben overwrite_policy=locked_context of only_stronger_source. Overschrijf die nooit stil met een openbare bron."),
        ("Confidence", "Getal van 0 tot en met 1. Feiten vereisen een verifieerbare bron; sociale media alleen is onvoldoende voor sterke financiële claims."),
        ("Relaties", "relation_class=juridisch is eigendom/zeggenschap; commercieel is lidmaatschap/samenwerking. Meng deze betekenissen nooit."),
        ("Identificatie", "Gebruik stabiele ASCII-sleutels, bijvoorbeeld cmp_demo_001, rel_demo_parent_001 en src_demo_001."),
        ("Datums", "ISO-datum yyyy-mm-dd. Landcodes zijn ISO 3166-1 alpha-2; valuta ISO 4217."),
        ("ChatGPT-opdracht", ""),
        ("KOPIEER VANAF HIER", """Ik upload een Excel-werkboek met schema_version=competitor_profile_v1.

Onderzoek per company_key de juridische entiteit en concernstructuur (directe moeder, ultimate parent, dochter- en zusterbedrijven) én commerciële verbanden. Controleer expliciet Quantore-lidmaatschap en vergelijkbare inkooporganisaties, coöperaties, franchise/formules, ketens, dealer-/retailnetwerken en brancheverbanden. Neem een commerciële relatie nooit aan als bewijs voor eigendom of zeggenschap.

Gebruik alleen verifieerbare openbare bronnen. Leg iedere claim vast in Bronnen en koppel source_id. Maak onzekerheid expliciet met status, information_layer en confidence. Gebruik status=unknown als iets niet is vastgesteld; gebruik nooit impliciet 0 of een lege cel als onbekend. Overschrijf Creditsafe-context niet met een zwakkere openbare bron; voeg zo nodig een aparte rij toe.

Vul Bedrijven en Relaties_Lidmaatschappen aan. Behoud exact dezelfde vier bladnamen, kolomnamen, volgorde, technische identifiers en schema_version. Voeg geen bladen of kolommen toe en vertaal technische keuzevelden niet. Lever het resultaat terug als geldig .xlsx-bestand met filters, vaste kopregel en bestaande validaties intact."""),
        ("KOPIEER TOT HIER", ""),
        ("V1 veldcatalogus", "Hieronder staan de toegestane field_key-waarden; nieuwe velden vereisen een nieuwe schemaversie."),
        ("field_key | datatype | herkomst | betekenis", ""),
    ]
    for row in rows:
        ws.append(row)
    for key, datatype, origin, meaning in FIELD_CATALOG:
        ws.append((key, f"{datatype} | {origin} | {meaning}"))
    ws["A1"].font = Font(bold=True, color="FFFFFF")
    ws["B1"].font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = PatternFill("solid", fgColor="1F4E78")
    for row in ws.iter_rows():
        row[0].font = Font(bold=True)
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[13].height = 235
    ws.freeze_panes = "A2"


def build_workbook(output: Path = OUTPUT) -> Path:
    wb = Workbook()
    build_instructions(wb)

    companies = wb.create_sheet("Bedrijven")
    companies.append(SHEETS["Bedrijven"])
    company_rows = [
        [SCHEMA_VERSION, "cmp_demo_001", "Voorbeeld Kantoorhandel B.V.", "legal_name",
         "Voorbeeld Kantoorhandel B.V.", None, None, None, None, None, "known",
         "feit", 0.95, "2026-01-15", "src_demo_creditsafe", "creditsafe",
         "locked_context", "Fictief voorbeeld; geen werkelijk bedrijf."],
        [SCHEMA_VERSION, "cmp_demo_001", "Voorbeeld Kantoorhandel B.V.", "kvk_number",
         "00000000", None, None, None, None, None, "known", "feit", 0.95,
         "2026-01-15", "src_demo_creditsafe", "creditsafe", "locked_context",
         "Fictief nummer."],
        [SCHEMA_VERSION, "cmp_demo_001", "Voorbeeld Kantoorhandel B.V.", "inventory_model",
         "hybride", None, None, None, None, None, "known", "schatting", 0.65,
         "2026-01-12", "src_demo_website", "openbare_bron", "enrichable",
         "Fictief voorbeeld."],
        [SCHEMA_VERSION, "cmp_demo_001", "Voorbeeld Kantoorhandel B.V.", "revenue_range_min",
         None, None, None, None, "EUR", None, "unknown", "schatting", 0.0,
         "2026-01-15", "src_demo_creditsafe", "creditsafe", "only_stronger_source",
         "Expliciet onbekend; geen impliciete nul."],
    ]
    for row in company_rows:
        companies.append(row)
    style_table(companies, "BedrijvenV1", {
        "company_key": 18, "company_name": 32, "field_key": 24, "value_text": 30,
        "notes": 38, "overwrite_policy": 22, "information_layer": 20,
    })

    relations = wb.create_sheet("Relaties_Lidmaatschappen")
    relations.append(SHEETS["Relaties_Lidmaatschappen"])
    relation_rows = [
        [SCHEMA_VERSION, "rel_demo_parent_001", "cmp_demo_001", "juridisch", "parent",
         "outgoing", "Voorbeeld Holding B.V.", "ext_demo_holding", "NL", "directe_moeder",
         "known", "feit", 0.90, "2026-01-10", "2020-01-01", None, "NL", "unknown",
         "src_demo_register", "Fictieve concernrelatie."],
        [SCHEMA_VERSION, "rel_demo_network_001", "cmp_demo_001", "commercieel",
         "inkooporganisatie", "outgoing", "Voorbeeld Inkoopnetwerk", "ext_demo_network",
         "NL", "lid", "known", "feit", 0.85, "2026-01-12", "2024-01-01", None,
         "NL", "yes", "src_demo_network", "Fictief commercieel lidmaatschap; geen eigendom."],
    ]
    for row in relation_rows:
        relations.append(row)
    style_table(relations, "RelatiesV1", {
        "relation_key": 24, "company_key": 18, "related_entity_name": 30,
        "relation_type": 24, "information_layer": 20, "notes": 42,
    })

    sources = wb.create_sheet("Bronnen")
    sources.append(SHEETS["Bronnen"])
    source_rows = [
        [SCHEMA_VERSION, "src_demo_creditsafe", "cmp_demo_001", "creditsafe",
         "Fictief Creditsafe-basisrapport", "Creditsafe", None, "2026-01-15",
         "2026-01-15", "hoog", "yes", "Voorbeeldbron; geen echt rapport."],
        [SCHEMA_VERSION, "src_demo_website", "cmp_demo_001", "bedrijfswebsite",
         "Fictieve fulfilmentpagina", "Voorbeeld Kantoorhandel", "https://example.invalid/bezorging",
         "2026-01-12", "2026-01-15", "middel", "partial", "Niet bezoeken; fictief voorbeeld."],
        [SCHEMA_VERSION, "src_demo_register", "cmp_demo_001", "kvk",
         "Fictief registeruittreksel", "KvK", None, "2026-01-10", "2026-01-15",
         "hoog", "yes", "Voorbeeldbron."],
        [SCHEMA_VERSION, "src_demo_network", "cmp_demo_001", "netwerkwebsite",
         "Fictieve ledenlijst", "Voorbeeld Inkoopnetwerk", "https://example.invalid/leden",
         "2026-01-12", "2026-01-15", "hoog", "yes", "Voorbeeldbron."],
    ]
    for row in source_rows:
        sources.append(row)
    style_table(sources, "BronnenV1", {
        "source_id": 22, "source_title": 32, "source_url": 38, "notes": 38,
    })

    for ws in (companies, relations, sources):
        for choice_name, values in CHOICES.items():
            if choice_name in SHEETS[ws.title]:
                add_choice(ws, choice_name, values)
        if "confidence" in SHEETS[ws.title]:
            col = SHEETS[ws.title].index("confidence") + 1
            dv = DataValidation(type="decimal", operator="between", formula1="0", formula2="1")
            dv.error = "Confidence moet tussen 0 en 1 liggen."
            dv.showErrorMessage = True
            ws.add_data_validation(dv)
            dv.add(f"{get_column_letter(col)}2:{get_column_letter(col)}1000")

    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return output


if __name__ == "__main__":
    print(build_workbook())