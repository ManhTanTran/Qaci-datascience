"""Optional, non-official Gemini Web adapter. Never called by offline commands."""
from __future__ import annotations

import os
import tempfile
import threading
from typing import Any

_WEBCLIENT_LOCK = threading.Lock()


async def collect_from_web(
    prompt: str,
    model: str | None = None,
    *,
    session_cookie: str | None = None,
    session_token: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    # UI callers pass credentials directly so they never need to mutate process
    # environment variables. CLI callers can continue to use environment values.
    cookie = (
        os.environ.get("GEMINI_SECURE_1PSID", "")
        if session_cookie is None
        else session_cookie
    )
    token = (
        os.environ.get("GEMINI_SECURE_1PSIDTS", "")
        if session_token is None
        else session_token
    )
    if not cookie:
        raise RuntimeError("Missing local GEMINI_SECURE_1PSID. No web call made.")
    # The library reads GEMINI_COOKIE_PATH from process environment and uses a
    # global logger. Serialize the short section that changes those globals,
    # including across Streamlit sessions.
    with _WEBCLIENT_LOCK:
        original_cache_path = os.environ.get("GEMINI_COOKIE_PATH")
        with tempfile.TemporaryDirectory(prefix="wardprice-webpilot-cookie-cache-") as cache_path:
            os.environ["GEMINI_COOKIE_PATH"] = cache_path
            try:
                try:
                    from gemini_webapi import GeminiClient
                    from loguru import logger
                except ImportError as exc:
                    raise RuntimeError(
                        "Install optional package: pip install gemini_webapi"
                    ) from exc
                # The wrapper may log response errors and cookie-cache paths. Keep
                # package logs out of terminal, files, and reports for this call.
                logger.disable("gemini_webapi")
                try:
                    client = GeminiClient(cookie, token or None, proxy=None, verbose=False)
                    try:
                        await client.init(timeout=45, auto_close=False, auto_refresh=False)
                        # The wrapper supports current_retry on its decorated request
                        # methods; keep this pilot to one generation attempt.
                        kwargs = {"current_retry": 0}
                        if model:
                            kwargs["model"] = model
                        result = await client.generate_content(prompt, **kwargs)
                        citations = []
                        for cite in getattr(result, "citations", []) or []:
                            citations.append(
                                {
                                    "title": getattr(cite, "title", None),
                                    "url": getattr(cite, "url", None),
                                }
                            )
                        return str(getattr(result, "text", "") or ""), citations
                    finally:
                        close = getattr(client, "close", None)
                        if close is not None:
                            await close()
                finally:
                    logger.enable("gemini_webapi")
            finally:
                if original_cache_path is None:
                    os.environ.pop("GEMINI_COOKIE_PATH", None)
                else:
                    os.environ["GEMINI_COOKIE_PATH"] = original_cache_path
