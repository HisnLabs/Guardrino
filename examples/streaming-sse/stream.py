"""Streaming through Guardrino. On a violation the stream ends with a final
`data: {"error": ...}` event and no [DONE]."""
import json, os
import httpx

url = "https://guardrino.your-company.example/v1/chat/completions"
headers = {"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"}
body = {"model": "gpt-4o", "stream": True,
        "messages": [{"role": "user", "content": "Write a short welcome message."}]}

with httpx.stream("POST", url, headers=headers, json=body, timeout=60) as r:
    for line in r.iter_lines():
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        evt = json.loads(data)
        if "error" in evt:
            print("\nStopped by Guardrino:", evt["error"].get("code"))
            break
        print(evt["choices"][0]["delta"].get("content", ""), end="", flush=True)
