#!/bin/bash
set -e
pnpm install --frozen-lockfile
uv pip install -r pyproject.toml
pnpm --filter @workspace/db push-force
