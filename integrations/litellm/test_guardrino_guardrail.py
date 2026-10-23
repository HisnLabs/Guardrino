import httpx, json, pytest, respx
import litellm
from fastapi import HTTPException
from guardrino_guardrail import GuardrinoGuardrail

URL = "http://guardrino.test"
EP = f"{URL}/v1/inspect"
pytestmark = pytest.mark.asyncio


def make(**kw):
    kw.setdefault("api_base", URL)
    kw.setdefault("tenant", "t1")
    kw.setdefault("app", "a1")
    return GuardrinoGuardrail(guardrail_name="guardrino", event_hook="pre_call", **kw)


def reply(action, text=None, forward="original"):
    d = {"request_id": "r", "action": action, "forward": forward}
    if text is not None:
        d["text"] = text
    return httpx.Response(200, json=d)


def pre(g, data):
    return g.async_pre_call_hook(None, None, data, "completion")


def resp(text):
    return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": text}}])


@respx.mock
async def test_input_allow_sends_payload():
    route = respx.post(EP).mock(return_value=reply("allow"))
    data = {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}],
            "user": "u7"}
    out = await pre(make(), data)
    body = json.loads(route.calls[0].request.content)
    assert body == {"text": "hi", "direction": "input", "tenant": "t1", "app": "a1",
                    "conversation_id": "u7", "user": "u7"}
    assert out["messages"][1]["content"] == "hi"


@respx.mock
async def test_conversation_id_from_metadata():
    route = respx.post(EP).mock(return_value=reply("allow"))
    await pre(make(), {"messages": [{"role": "user", "content": "hi"}],
                       "metadata": {"conversation_id": "c9"}})
    assert json.loads(route.calls[0].request.content)["conversation_id"] == "c9"


@respx.mock
async def test_only_last_user_message_inspected():
    route = respx.post(EP).mock(return_value=reply("allow"))
    await pre(make(), {"messages": [{"role": "user", "content": "old"},
                                    {"role": "assistant", "content": "x"},
                                    {"role": "user", "content": "new"}]})
    assert [json.loads(c.request.content)["text"] for c in route.calls] == ["new"]


@respx.mock
async def test_tool_messages_sent_as_context():
    route = respx.post(EP).mock(return_value=reply("allow"))
    await pre(make(), {"messages": [{"role": "user", "content": "q"},
                                    {"role": "tool", "content": "doc text", "tool_call_id": "1"},
                                    {"role": "function", "content": "fn out", "name": "f"}]})
    seen = [(json.loads(c.request.content)["direction"], json.loads(c.request.content)["text"])
            for c in route.calls]
    assert ("input", "q") in seen and ("context", "doc text") in seen and ("context", "fn out") in seen


@respx.mock
@pytest.mark.parametrize("action", ["block", "refused", "rephrase"])
async def test_input_block_raises_400(action):
    respx.post(EP).mock(return_value=reply(action))
    with pytest.raises(HTTPException) as e:
        await pre(make(), {"messages": [{"role": "user", "content": "bad"}]})
    assert e.value.status_code == 400


@respx.mock
async def test_input_403_from_guardrino_is_violation():
    respx.post(EP).mock(return_value=httpx.Response(403, json={"blocked": True, "request_id": "r", "action": "block"}))
    with pytest.raises(HTTPException) as e:
        await pre(make(), {"messages": [{"role": "user", "content": "bad"}]})
    assert e.value.status_code == 400


@respx.mock
async def test_input_mask_replaces_text():
    respx.post(EP).mock(return_value=reply("mask", "my card is [CARD]", "masked"))
    data = {"messages": [{"role": "user", "content": "my card is 4111"}]}
    out = await pre(make(), data)
    assert out["messages"][0]["content"] == "my card is [CARD]"


@respx.mock
async def test_context_mask_replaces_tool_text():
    respx.post(EP).mock(side_effect=lambda r: reply("mask", "[M]") if json.loads(r.content)["direction"] == "context" else reply("allow"))
    out = await pre(make(), {"messages": [{"role": "user", "content": "q"},
                                          {"role": "tool", "content": "secret", "tool_call_id": "1"}]})
    assert out["messages"][1]["content"] == "[M]"
    assert out["messages"][0]["content"] == "q"


@respx.mock
async def test_input_warn_allows_and_notes_metadata():
    respx.post(EP).mock(return_value=reply("warn"))
    out = await pre(make(), {"messages": [{"role": "user", "content": "hmm"}]})
    assert out["messages"][0]["content"] == "hmm"
    assert out["metadata"]["guardrino_action"] == "warn"


@respx.mock
async def test_context_block_raises():
    respx.post(EP).mock(side_effect=lambda r: reply("block") if json.loads(r.content)["direction"] == "context" else reply("allow"))
    with pytest.raises(HTTPException):
        await pre(make(), {"messages": [{"role": "user", "content": "q"},
                                        {"role": "tool", "content": "inj", "tool_call_id": "1"}]})


@respx.mock
async def test_list_content_text_parts():
    route = respx.post(EP).mock(return_value=reply("mask", "X"))
    out = await pre(make(), {"messages": [{"role": "user", "content": [{"type": "text", "text": "a"}]}]})
    assert json.loads(route.calls[0].request.content)["text"] == "a"
    assert out["messages"][0]["content"][0]["text"] == "X"


# ---- output ----
@respx.mock
async def test_output_allow_sends_output_direction():
    route = respx.post(EP).mock(return_value=reply("allow"))
    r = resp("hello")
    await make().async_post_call_success_hook({"user": "u"}, None, r)
    assert json.loads(route.calls[0].request.content)["direction"] == "output"
    assert r.choices[0].message.content == "hello"


@respx.mock
@pytest.mark.parametrize("action", ["block", "refused"])
async def test_output_block_raises(action):
    respx.post(EP).mock(return_value=reply(action))
    with pytest.raises(HTTPException) as e:
        await make().async_post_call_success_hook({}, None, resp("leak"))
    assert e.value.status_code == 400


@respx.mock
async def test_output_mask_replaces():
    respx.post(EP).mock(return_value=reply("mask", "call [PHONE]", "masked"))
    r = resp("call +971500000000")
    await make().async_post_call_success_hook({}, None, r)
    assert r.choices[0].message.content == "call [PHONE]"


@respx.mock
async def test_output_warn_allows():
    respx.post(EP).mock(return_value=reply("warn"))
    r = resp("ok")
    await make().async_post_call_success_hook({}, None, r)
    assert r.choices[0].message.content == "ok"


# ---- failures ----
@respx.mock
async def test_timeout_fail_open_default():
    respx.post(EP).mock(side_effect=httpx.ReadTimeout("slow"))
    data = {"messages": [{"role": "user", "content": "hi"}]}
    out = await pre(make(), data)
    assert out["messages"][0]["content"] == "hi"


@respx.mock
async def test_timeout_fail_closed():
    respx.post(EP).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(HTTPException) as e:
        await pre(make(fail_open=False), {"messages": [{"role": "user", "content": "hi"}]})
    assert e.value.status_code == 503


@respx.mock
async def test_server_error_fail_open_and_closed():
    respx.post(EP).mock(return_value=httpx.Response(500))
    r = resp("x")
    await make().async_post_call_success_hook({}, None, r)
    with pytest.raises(HTTPException):
        await make(fail_open=False).async_post_call_success_hook({}, None, resp("x"))


@respx.mock
async def test_connect_error_fail_closed():
    respx.post(EP).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(HTTPException):
        await pre(make(fail_open=False), {"messages": [{"role": "user", "content": "hi"}]})


async def test_env_defaults(monkeypatch):
    monkeypatch.setenv("GUARDRINO_URL", "http://env.test")
    monkeypatch.setenv("GUARDRINO_FAIL_OPEN", "false")
    monkeypatch.setenv("GUARDRINO_TIMEOUT", "1.5")
    g = GuardrinoGuardrail(guardrail_name="g", event_hook="pre_call")
    assert g.api_base == "http://env.test" and g.fail_open is False and g.timeout_s == 1.5
