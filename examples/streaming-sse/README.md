# Streaming (SSE)

Events are forwarded as they arrive and the accumulated reply is checked periodically and once more before `[DONE]`.
Chunks already sent cannot be recalled. If that matters for your data, enable output buffering on the gateway
(`[proxy] buffer_output = true`): the whole reply is checked before anything is sent.
