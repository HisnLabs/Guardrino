# MCP: agent, Guardrino, MCP server

```
agent  ->  https://guardrino.your-company.example/mcp/files  ->  MCP server (files)
```

1. Declare the server in the gateway: [gateway.toml](gateway.toml).
2. Point the agent's MCP client at `/mcp/<name>` (streamable HTTP): [agent-config.json](agent-config.json).

Tool descriptions, tool-call arguments and tool results are inspected; a poisoned tool is dropped from `tools/list`.
