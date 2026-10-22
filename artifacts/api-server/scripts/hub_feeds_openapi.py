"""Generate Hub feeds + printer contracts without app startup or database access."""
import json
import re
import sys
import textwrap
from pathlib import Path

import yaml
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routes.hub_feeds import router as feeds
from routes.printer_workflow import router as printer


target = Path(__file__).resolve().parents[3] / "lib/api-spec/openapi.yaml"
original = target.read_text()
for label, prefix, router in (("HUBFEEDS", "HubFeeds", feeds), ("PRINTERWORKFLOW", "PrinterWorkflow", printer)):
    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()
    names = schema.get("components", {}).get("schemas", {})
    text = json.dumps(schema)
    for name in sorted(names, key=len, reverse=True):
        text = text.replace(f'#/components/schemas/{name}"', f'#/components/schemas/{prefix}{name}"')
    schema = json.loads(text)
    schemas = {prefix + name: value for name, value in schema["components"]["schemas"].items()}
    paths = {}
    for path, value in schema["paths"].items():
        for method, operation in value.items():
            if isinstance(operation, dict) and "operationId" in operation:
                name = operation["operationId"].split("_api_")[0]
                operation["operationId"] = prefix[0].lower() + prefix[1:] + name.title().replace("_", "")
                if method == "get" and ("/download" in path or path.endswith("/feed")):
                    media = "text/csv" if prefix == "HubFeeds" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    operation["responses"]["200"]["content"] = {media: {"schema": {"type": "string", "format": "binary"}}}
        paths[path.removeprefix("/api")] = value
    for kind in ("PATHS", "SCHEMAS"):
        original = re.sub(rf" *# {label} {kind} BEGIN\n.*? *# {label} {kind} END\n", "", original, flags=re.S)

    def block(kind, values, indent):
        return (f"{indent}# {label} {kind} BEGIN\n" +
                textwrap.indent(yaml.safe_dump(values, sort_keys=False, allow_unicode=True, width=120), indent) +
                f"{indent}# {label} {kind} END\n")

    original = original.replace("paths:\n", "paths:\n" + block("PATHS", paths, "  "), 1)
    original = original.replace("  schemas:\n", "  schemas:\n" + block("SCHEMAS", schemas, "    "), 1)
target.write_text(original)
