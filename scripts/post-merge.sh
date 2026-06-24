#!/bin/bash
set -e
pnpm install --frozen-lockfile
uv pip install -r artifacts/api-server/requirements.txt
pnpm --filter @workspace/db push-force
