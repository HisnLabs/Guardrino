import json, os, socket, subprocess, sys, time
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
ROOT = PLUGIN.parent.parent
DEVAPI = ROOT / "target/debug/guardrino-devapi"
KEY = "e2e-test-key"
L2 = os.environ.get("GUARDRINO_L2_URL", "http://localhost:8810")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait(url, timeout=90, ok=lambda r: r.status_code < 500, proc=None):
    end = time.time() + timeout
    while time.time() < end:
        if proc is not None and proc.p.poll() is not None:
            raise RuntimeError(f"process exited: {url}")
        try:
            if ok(httpx.get(url, timeout=2)):
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"not up: {url}")


class Proc:
    def __init__(self, cmd, env=None, cwd=None, log=None):
        self.log = open(log, "wb")
        self.p = subprocess.Popen(cmd, env={**os.environ, **(env or {})}, cwd=cwd, stdout=self.log, stderr=subprocess.STDOUT)

    def stop(self):
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(10)
            except subprocess.TimeoutExpired:
                self.p.kill()
        self.log.close()


def policy_text(audit: Path, proxy_upstream: str | None = None) -> str:
    t = f'''mode = "enforce"
[l1]
personal_data = "mask"
secret = "mask"
[l2]
action = "block"
timeout_ms = 3000
on_error = "allow"
[canary]
enabled = true
action = "block"
[audit]
enabled = true
path = "{audit}"
'''
    if proxy_upstream:
        t += f'[proxy]\nupstream = "{proxy_upstream}"\napi_key = "{KEY}"\n'
    return t


def start_guardrino(tmp: Path, name: str, proxy_upstream=None):
    try:
        httpx.get(L2 + "/health", timeout=2).raise_for_status()
    except httpx.HTTPError:
        pytest.skip(f"L2 guard not running at {L2}")
    if not DEVAPI.exists():
        pytest.skip("debug build of guardrino-devapi missing")
    port = free_port()
    pol = tmp / f"{name}.toml"
    pol.write_text(policy_text(tmp / f"{name}-audit.jsonl", proxy_upstream))
    pr = Proc([str(DEVAPI)], env={"GUARDRINO_POLICY": str(pol), "GUARDRINO_DEVAPI_PORT": str(port),
                                  "GUARDRINO_DEVAPI_L2": L2}, cwd=str(tmp), log=tmp / f"{name}.log")
    wait(f"http://127.0.0.1:{port}/health", 30, lambda r: True)
    return pr, f"http://127.0.0.1:{port}"


@pytest.fixture(scope="session")
def tmp(tmp_path_factory):
    return tmp_path_factory.mktemp("e2e")


@pytest.fixture(scope="session")
def mock(tmp):
    port = free_port()
    pr = Proc([sys.executable, str(HERE / "mock_upstream.py"), str(port)], log=tmp / "mock.log")
    url = f"http://127.0.0.1:{port}"
    wait(url + "/_received")
    yield url
    pr.stop()


@pytest.fixture(scope="session")
def guardrino(tmp):
    pr, url = start_guardrino(tmp, "plugin")
    holder = {"proc": pr, "url": url}
    yield holder
    holder["proc"].stop()


@pytest.fixture(scope="session")
def litellm(tmp, mock, guardrino):
    port = free_port()
    exe = Path(sys.executable).parent / "litellm"
    pr = Proc([str(exe), "--config", str(HERE / "config.yaml"), "--port", str(port), "--host", "127.0.0.1"],
              env={"MOCK_UPSTREAM_URL": mock, "GUARDRINO_URL": guardrino["url"],
                   "PYTHONPATH": str(PLUGIN), "LITELLM_MASTER_KEY": KEY, "LITELLM_LOG": "INFO"}, cwd=str(PLUGIN), log=tmp / "litellm.log")
    url = f"http://127.0.0.1:{port}"
    wait(url + "/health/liveliness", 120, proc=pr)
    yield url
    pr.stop()


def chat(base, content, model="mock-gpt", **kw):
    body = {"model": model, "messages": [{"role": "user", "content": content}]}
    body.update(kw)
    return httpx.post(base + "/v1/chat/completions", timeout=60, headers={"authorization": "Bearer " + KEY}, json=body)


@pytest.fixture
def received(mock):
    httpx.delete(mock + "/_received")
    return lambda: httpx.get(mock + "/_received").json()
