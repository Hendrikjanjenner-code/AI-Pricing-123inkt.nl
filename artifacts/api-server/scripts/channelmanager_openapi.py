"""Merge isolated router schema into shared contract, without starting the application."""
import json
import sys
import re
import textwrap
from pathlib import Path
import yaml
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routes.channelmanager import router

app = FastAPI()
app.include_router(router)
schema = app.openapi()
target = Path(__file__).resolve().parents[3] / "lib/api-spec/openapi.yaml"
# Prefix schemas to avoid collisions with other services' Notes/ValidationError.
names = schema.get("components", {}).get("schemas", {})
text = json.dumps(schema)
for name in sorted(names, key=len, reverse=True):
    text = text.replace(f'#/components/schemas/{name}"', f'#/components/schemas/Channel{name}"')
schema = json.loads(text)
schemas = {"Channel" + name: value for name, value in schema["components"]["schemas"].items()}
paths = {}
for path, value in schema["paths"].items():
    for method, operation in value.items():
        if isinstance(operation, dict) and "operationId" in operation:
            operation["operationId"] = "channel" + operation["operationId"].split("_api_channelmanager")[0].title().replace("_", "")
    paths[path.removeprefix("/api")] = value
original = target.read_text()
for label in ("PATHS", "SCHEMAS"):
    original = re.sub(rf" *# CHANNELMANAGER {label} BEGIN\n.*? *# CHANNELMANAGER {label} END\n", "", original, flags=re.S)
def block(label, values, indent):
    return (f"{indent}# CHANNELMANAGER {label} BEGIN\n" +
            textwrap.indent(yaml.safe_dump(values, sort_keys=False, allow_unicode=True, width=120), indent) +
            f"{indent}# CHANNELMANAGER {label} END\n")
original = original.replace("paths:\n", "paths:\n" + block("PATHS", paths, "  "), 1)
original = original.replace("  schemas:\n", "  schemas:\n" + block("SCHEMAS", schemas, "    "), 1)
target.write_text(original)
