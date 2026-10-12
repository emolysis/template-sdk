#!/usr/bin/env bash
# PostToolUse hook: format the file Claude just wrote. Never blocks the
# session; formatting problems surface later in `task gate`.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

file=$(python3 -c 'import json, sys; print((json.load(sys.stdin).get("tool_input") or {}).get("file_path", ""))' 2>/dev/null) || exit 0
[ -n "$file" ] && [ -f "$file" ] || exit 0

ruff=.venv/bin/ruff
[ -x "$ruff" ] || ruff=$(command -v ruff || true)
prettier=node_modules/.bin/prettier

case "$file" in
  *.py | *.pyi)
    [ -n "$ruff" ] && { "$ruff" format --quiet "$file"; "$ruff" check --quiet --fix "$file"; }
    ;;
  *.ts | *.tsx | *.js | *.jsx | *.mjs | *.cjs | *.json | *.css | *.md | *.yml | *.yaml | *.astro)
    [ -x "$prettier" ] && "$prettier" --write --log-level warn "$file"
    ;;
esac
exit 0
