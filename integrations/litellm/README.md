# Guardrino guardrail for LiteLLM

A `CustomGuardrail` that sends traffic to Guardrino `POST /v1/inspect`.

- `pre_call`: the last user message is inspected as `input`; `tool`/`function` messages as `context`.
- `post_call`: the assistant reply is inspected as `output`.
- `block`, `refused`, `rephrase` (or HTTP 403 from Guardrino): HTTP 400 `HTTPException`.
- `mask`: the message text is replaced with Guardrino's `text`.
- `warn`: allowed; `metadata.guardrino_action = "warn"` and `guardrino_request_id` are set.
- Guardrino unreachable, timeout or 5xx: allowed (fail-open, default) or HTTP 503 (fail-closed).
- Streaming: `post_call` does not cover streamed responses.

## Install

```
pip install guardrino-litellm     # or, from this folder: pip install .
```
Reference it in `config.yaml` as `guardrail: guardrino_litellm.GuardrinoGuardrail` (see `config.yaml` here), then
`litellm --config config.yaml`. The old `guardrino_guardrail.GuardrinoGuardrail` path still imports.
LiteLLM's proxy refuses to start without `LITELLM_MASTER_KEY`.

## Settings (litellm_params, or env)

| Param | Env | Default |
|---|---|---|
| `api_base` | `GUARDRINO_URL` | `http://127.0.0.1:8787` |
| `tenant` | `GUARDRINO_TENANT` | `litellm` |
| `app` | `GUARDRINO_APP` | `litellm` |
| `fail_open` | `GUARDRINO_FAIL_OPEN` | `true` |
| `timeout` (s) | `GUARDRINO_TIMEOUT` | `5` |

`conversation_id` comes from `metadata.conversation_id`, else the request `user`.

## Option B: no plugin

Run Guardrino's OpenAI-compatible proxy in front and set LiteLLM as its upstream: clients call Guardrino, Guardrino
inspects both directions and forwards to LiteLLM (`http://litellm:4000/v1`). Use this for streaming coverage or when
you cannot load Python plugins. See the Guardrino docs for the proxy upstream setting.

## Tests

```
uv venv && uv pip install litellm fastapi pytest pytest-asyncio respx httpx && .venv/bin/python -m pytest
```

## End-to-end tests (real processes)

`e2e/` starts a mock OpenAI upstream, the Guardrino dev API (debug build, enforce, L1 + L2, canary) and a real
`litellm` proxy on free ports, then sends HTTP requests. Needs the L2 guard on `http://localhost:8810`
(`GUARDRINO_L2_URL` to change) and `cargo build -p guardrino-devapi` done once (debug).

```
uv venv && uv pip install "litellm[proxy]" pytest pytest-asyncio respx httpx build twine
.venv/bin/python -m pytest -m e2e e2e        # 6 tests: safe, attack, masked Emirates ID, leaked canary, fail-open, Guardrino-in-front chain
.venv/bin/python -m pytest                   # unit tests only (e2e is deselected by default)
```

## Publish to PyPI (owner)

Not uploaded by the build. Steps, using Trusted Publishing (no token stored):

1. Build and check locally: `python -m build && twine check dist/*` (wheel and sdist land in `dist/`).
2. On pypi.org: Account, Publishing, add a pending publisher: project `guardrino-litellm`, owner/repo of the
   repository, workflow file name (e.g. `publish-litellm.yml`), environment `pypi`.
3. In that GitHub workflow: `permissions: id-token: write`, run on a `litellm-v*` tag, build in
   `integrations/litellm`, then `pypa/gh-action-pypi-publish@release/v1` with `packages-dir: integrations/litellm/dist`
   and `environment: pypi` (add required reviewers to that environment).
4. Test first on TestPyPI with a second pending publisher (`repository-url: https://test.pypi.org/legacy/`).

Note: the end-to-end tests need a Guardrino gateway build, which is commercial and not part of this repository.
The unit tests do not. Ask for access at contact@hisnlabs.com.
