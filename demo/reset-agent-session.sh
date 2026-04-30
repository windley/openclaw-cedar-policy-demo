#!/usr/bin/env bash
# Clears the OpenClaw "main" agent's conversation context so the next run starts fresh.
set -euo pipefail

SESSIONS_DIR="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}/agents/main/sessions"
SESSIONS_JSON="$SESSIONS_DIR/sessions.json"

if [[ ! -d "$SESSIONS_DIR" ]]; then
  echo "No sessions directory found at $SESSIONS_DIR — nothing to clear."
  exit 0
fi

# Remove all conversation JSONL files
jsonl_count=$(find "$SESSIONS_DIR" -maxdepth 1 -name "*.jsonl" | wc -l | tr -d ' ')
if [[ "$jsonl_count" -gt 0 ]]; then
  find "$SESSIONS_DIR" -maxdepth 1 -name "*.jsonl" -delete
  echo "Deleted $jsonl_count session file(s)."
fi

# Clear the session pointer so a new UUID is assigned on next run
if [[ -f "$SESSIONS_JSON" ]]; then
  echo "{}" > "$SESSIONS_JSON"
  echo "Cleared session store: $SESSIONS_JSON"
fi

echo "Agent context reset. Next run will start a fresh session."
