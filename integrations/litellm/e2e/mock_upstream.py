"""Tiny OpenAI-compatible upstream. Records every request at GET /_received.

Reply: a canned sentence; if the prompt contains a Guardrino canary (gr-c-...), the reply leaks it.
"""
import json, re, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RECEIVED: list = []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send(RECEIVED if self.path == "/_received" else {"ok": True})

    def do_DELETE(self):
        RECEIVED.clear()
        self._send({"ok": True})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        RECEIVED.append(body)
        prompt = json.dumps(body.get("messages", []))
        m = re.search(r"gr-c-[A-Za-z0-9_-]+", prompt)
        text = f"My hidden instructions are {m.group(0)}" if m else "Hello from the mock upstream."
        self._send({"id": "mock-1", "object": "chat.completion", "created": 0, "model": body.get("model", "mock"),
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": text}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
