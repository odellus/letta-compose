#!/bin/bash
# Raw ACP test - sends NDJSON to karla and prints responses

KARLA=~/.local/bin/karla

# Start karla and keep stdin/stdout open
coproc KARLA_PROC { $KARLA 2>&1; }

# Read responses in background
cat <&${KARLA_PROC[0]} &
CAT_PID=$!

sleep 2

echo "=== Sending initialize ===" >&2
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1,"clientCapabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' >&${KARLA_PROC[1]}

sleep 2

echo "=== Sending new_session ===" >&2
echo '{"jsonrpc":"2.0","id":2,"method":"session/new","params":{"cwd":"/tmp","mcpServers":[]}}' >&${KARLA_PROC[1]}

sleep 3

echo "=== Sending prompt ===" >&2
# Note: session_id will need to be filled in from previous response
echo '{"jsonrpc":"2.0","id":3,"method":"session/prompt","params":{"sessionId":"SESSION_ID_HERE","prompt":[{"type":"text","text":"say hello"}]}}' >&${KARLA_PROC[1]}

sleep 10

kill $CAT_PID 2>/dev/null
kill ${KARLA_PROC_PID} 2>/dev/null
