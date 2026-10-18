"""Optional Deep Research client; never imported by offline parsing commands."""

from __future__ import annotations

import os
import tempfile
from typing import Any


def _plan_payload(plan: Any) -> dict[str, Any]:
    """Return research-plan fields only, omitting session metadata and credentials."""
    fields = (
        "research_id",
        "title",
        "query",
        "steps",
        "eta_text",
        "confirm_prompt",
        "modify_prompt",
        "confirmation_url",
    )
    return {name: getattr(plan, name, None) for name in fields}


def _source_payload(source: Any) -> dict[str, Any]:
    return {
        "id": getattr(source, "id", None),
        "title": getattr(source, "title", None),
        "url": getattr(source, "url", None),
        "favicon": getattr(source, "favicon", None),
    }


async def run_deep_research(
    prompt: str,
    *,
    model: str | None = None,
    poll_interval: float = 10.0,
    timeout: float = 600.0,
) -> dict[str, Any]:
    """Run one plan/start/poll workflow and return the document and citation objects.

    This function makes no source-page requests and never writes files or a database.
    The upstream wrapper controls its own low-level retries and chat recovery.
    """
    cookie = os.environ.get("GEMINI_SECURE_1PSID", "")
    token = os.environ.get("GEMINI_SECURE_1PSIDTS", "")
    if not cookie:
        raise RuntimeError("Missing local GEMINI_SECURE_1PSID; no web request made")

    original_cache_path = os.environ.get("GEMINI_COOKIE_PATH")
    with tempfile.TemporaryDirectory(prefix="wardprice-deep-research-cookie-cache-") as cache_path:
        os.environ["GEMINI_COOKIE_PATH"] = cache_path
        try:
            try:
                from gemini_webapi import GeminiClient
                from loguru import logger
            except ImportError as exc:
                raise RuntimeError("Install optional package: pip install gemini_webapi") from exc

            logger.disable("gemini_webapi")
            try:
                client = GeminiClient(cookie, token or None, proxy=None, verbose=False)
                try:
                    await client.init(timeout=45, auto_close=False, auto_refresh=False)
                    chat = client.start_chat(model=model)
                    plan = await client.create_deep_research_plan(prompt, chat=chat)
                    start_output = await client.start_deep_research(plan, chat=chat)
                    result = await client.wait_for_deep_research(
                        plan,
                        poll_interval=poll_interval,
                        timeout=timeout,
                    )
                    document = getattr(result, "document", None)
                    # Some wrapper versions attach the report to the start turn.
                    if document is None:
                        document = getattr(start_output, "deep_research_document", None)
                    sources = getattr(document, "sources", []) if document is not None else []
                    return {
                        "plan": _plan_payload(plan),
                        "done": bool(getattr(result, "done", False)),
                        "document_id": getattr(document, "id", None),
                        "document_title": getattr(document, "title", None),
                        "document_text": str(getattr(document, "content", "") or ""),
                        "sources": [_source_payload(source) for source in sources or []],
                    }
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
