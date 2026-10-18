"""Thin wrapper around the Anthropic client shared by the extract and verify steps."""

import os

import anthropic

MODEL = os.getenv("VERIFACT_MODEL", "claude-opus-5-5")

# Server-side refusal fallback: if the primary model declines a request, the API
# re-runs it on a fallback model inside the same call instead of returning nothing.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class RefusalError(RuntimeError):
    pass


def make_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key, max_retries=4, timeout=300.0)


def create_message(client: anthropic.Anthropic, **kwargs):
    response = client.beta.messages.create(
        model=MODEL,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        **kwargs,
    )
    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None) if response.stop_details else None
        raise RefusalError(f"Model declined the request (category: {category})")
    return response
