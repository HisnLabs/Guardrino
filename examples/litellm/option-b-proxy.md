# LiteLLM, option B: Guardrino in front (no plugin)

Clients call Guardrino's OpenAI-compatible proxy; Guardrino inspects both directions and forwards to LiteLLM.

```
client -> https://guardrino.your-company.example/v1/chat/completions
       -> Guardrino (inspects input and output)
       -> LiteLLM  http://litellm:4000/v1  (the gateway's `[proxy] upstream`)
```

Use this when you need streaming coverage or cannot load Python plugins. For the plugin route, see
`option-a-plugin.config.yaml` and `integrations/litellm/`.
