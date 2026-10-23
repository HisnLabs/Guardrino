# Copyright 2026 HisnLabs. Licensed under the Apache License, Version 2.0.
"""LiteLLM custom guardrail that asks a Guardrino gateway to inspect traffic."""
import os
from typing import Any, Optional

import httpx
from fastapi import HTTPException
from litellm.integrations.custom_guardrail import CustomGuardrail

BLOCKING = {"block", "refused", "rephrase"}
CONTEXT_ROLES = {"tool", "function"}


def _truthy(v: str) -> bool:
    return v.strip().lower() not in ("0", "false", "no", "off")


class GuardrinoGuardrail(CustomGuardrail):
    def __init__(self, api_base: Optional[str] = None, tenant: Optional[str] = None,
                 app: Optional[str] = None, fail_open: Optional[bool] = None,
                 timeout: Optional[float] = None, **kwargs):
        self.api_base = (api_base or os.getenv("GUARDRINO_URL", "http://127.0.0.1:8787")).rstrip("/")
        self.tenant = tenant or os.getenv("GUARDRINO_TENANT", "litellm")
        self.app = app or os.getenv("GUARDRINO_APP", "litellm")
        self.fail_open = fail_open if fail_open is not None else _truthy(os.getenv("GUARDRINO_FAIL_OPEN", "true"))
        self.timeout_s = float(timeout if timeout is not None else os.getenv("GUARDRINO_TIMEOUT", "5"))
        kwargs.pop("timeout", None)
        super().__init__(**kwargs)

    # ---- Guardrino call ----
    async def _inspect(self, text: str, direction: str, data: dict) -> Optional[dict]:
        """Returns the decision, or None when Guardrino failed and fail_open is set."""
        meta = data.get("metadata") or {}
        user = data.get("user") or meta.get("user_api_key_user_id")
        conv = meta.get("conversation_id") or data.get("user")
        body = {"text": text, "direction": direction, "tenant": self.tenant, "app": self.app}
        if conv:
            body["conversation_id"] = str(conv)
        if user:
            body["user"] = str(user)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                r = await c.post(f"{self.api_base}/v1/inspect", json=body)
            if r.status_code == 403:
                return {"action": "block", **(r.json() if r.content else {})}
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            if self.fail_open:
                return None
            raise HTTPException(status_code=503, detail={"error": "Guardrino unavailable", "reason": type(e).__name__})

    def _violation(self, d: dict, direction: str) -> HTTPException:
        return HTTPException(status_code=400, detail={
            "error": f"Blocked by Guardrino ({direction})",
            "action": d.get("action"), "request_id": d.get("request_id")})

    async def _apply(self, text: str, direction: str, data: dict) -> Optional[str]:
        """Returns replacement text for mask, else None; raises on block."""
        d = await self._inspect(text, direction, data)
        if d is None:
            return None
        action = d.get("action")
        if action in BLOCKING:
            raise self._violation(d, direction)
        if action == "warn":
            md = data.setdefault("metadata", {})
            md["guardrino_action"] = "warn"
            md["guardrino_request_id"] = d.get("request_id")
        if action == "mask" and d.get("text") is not None:
            return d["text"]
        return None

    # ---- input ----
    async def async_pre_call_hook(self, user_api_key_dict, cache, data: dict, call_type) -> Any:
        messages = data.get("messages") or []
        last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=None)
        for i, m in enumerate(messages):
            if i == last_user:
                direction = "input"
            elif m.get("role") in CONTEXT_ROLES:
                direction = "context"
            else:
                continue
            c = m.get("content")
            if isinstance(c, str):
                if c:
                    new = await self._apply(c, direction, data)
                    if new is not None:
                        m["content"] = new
            elif isinstance(c, list):
                for part in c:
                    if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                        new = await self._apply(part["text"], direction, data)
                        if new is not None:
                            part["text"] = new
        return data

    # ---- output ----
    async def async_post_call_success_hook(self, data: dict, user_api_key_dict, response) -> Any:
        for ch in getattr(response, "choices", None) or []:
            msg = getattr(ch, "message", None)
            text = getattr(msg, "content", None)
            if isinstance(text, str) and text:
                new = await self._apply(text, "output", data)
                if new is not None:
                    msg.content = new
        return response
