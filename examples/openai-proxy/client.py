"""OpenAI Python SDK through Guardrino: change base_url, nothing else."""
import os
from openai import OpenAI, APIStatusError

client = OpenAI(
    base_url="https://guardrino.your-company.example/v1",
    api_key=os.environ["LLM_API_KEY"],
    default_headers={"X-Guardrino-Tenant": "acme", "X-Guardrino-App": "support-bot"},
)

try:
    r = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
        user="conv-1234",  # conversation id (or send X-Guardrino-Conversation)
    )
    print(r.choices[0].message.content)
except APIStatusError as e:
    if e.status_code in (400, 403):
        print("Blocked by Guardrino:", e.body)
    else:
        raise
