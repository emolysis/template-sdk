#!/usr/bin/env bash
# SessionStart hook: install the toolchain and dependencies in Claude Code
# cloud sessions so `task gate` works from the first prompt. Local sessions
# are left alone; run `task setup` yourself there.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"

if ! command -v task >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then
    uv tool install --quiet go-task-bin
  else
    npm install --global --silent @go-task/cli
  fi
  export PATH="$HOME/.local/bin:$PATH"
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
  fi
fi

task setup
