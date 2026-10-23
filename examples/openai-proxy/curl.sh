#!/bin/sh
# Same request you send to your LLM provider; only the base URL changes.
curl -sS https://guardrino.your-company.example/v1/chat/completions \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Guardrino-Tenant: acme" \
  -H "X-Guardrino-App: support-bot" \
  -H "X-Guardrino-Conversation: conv-1234" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Hello"}]}'
# A refused request returns {"error":{"type":"guardrino_blocked","code":"content_blocked",...}} (HTTP 403 or 400).
