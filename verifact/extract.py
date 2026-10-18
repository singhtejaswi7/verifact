"""Step 1: pull specific, checkable claims out of a PDF."""

import base64
import json
from dataclasses import dataclass
from datetime import date

import anthropic

from .client import create_message

CATEGORIES = ["statistic", "date", "financial", "technical", "other"]

EXTRACT_SYSTEM = """You extract checkable factual claims from documents so they can be fact-checked against the public web.

Extract claims that contain a specific, verifiable fact about the world:
- statistics and percentages (user counts, market share, survey results, growth rates)
- dates and timelines (launches, founding years, events, deadlines)
- financial figures (revenue, valuations, funding rounds, market size, prices)
- technical figures (specs, benchmarks, model sizes, performance numbers)
- superlatives and records tied to a named entity ("the largest", "the first")

Skip opinions, vague marketing language, predictions, and purely internal claims that no public source could confirm (for example "our team grew 3x"). Merge duplicates.

For each claim, write `claim` as a standalone sentence that someone with no access to the document could search for: name the subject, the figure, and any timeframe the document gives. Copy the original wording into `quote`. Use 1-based page numbers, or 0 if unsure."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "quote": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "page": {"type": "integer"},
                },
                "required": ["claim", "quote", "category", "page"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}


@dataclass
class Claim:
    id: int
    claim: str
    quote: str
    category: str
    page: int


def extract_claims(client: anthropic.Anthropic, pdf_bytes: bytes, max_claims: int) -> list[Claim]:
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    response = create_message(
        client,
        max_tokens=16000,
        system=EXTRACT_SYSTEM,
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": EXTRACT_SCHEMA},
        },
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Today's date is {date.today().isoformat()}. Extract up to {max_claims} claims "
                            "from this document. If there are more, keep the most specific and consequential ones."
                        ),
                    },
                ],
            }
        ],
    )
    text = next(b.text for b in reversed(response.content) if b.type == "text")
    raw = json.loads(text)["claims"][:max_claims]
    return [Claim(id=i + 1, **c) for i, c in enumerate(raw)]
