from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from google import genai


load_dotenv()

DEFAULT_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash",
)


@dataclass(frozen=True)
class GeminiResult:
    facts: tuple[dict[str, Any], ...]
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    attempts: int


class GeminiAgent:
    """
    Gemini Interactions API wrapper.

    The model extracts evidence only.
    Financial affordability is decided by the deterministic engine.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_retries: int = 3,
        timeout_seconds: int = 30,
    ):
        api_key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )

        if not api_key:
            raise RuntimeError(
                "Missing GEMINI_API_KEY or GOOGLE_API_KEY."
            )

        self.model = model
        self.max_retries = max_retries

        # The SDK reads GEMINI_API_KEY automatically, but passing the
        # environment variable explicitly keeps local configuration clear.
        self.client = genai.Client(
            api_key=api_key,
        )

        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _prompt(prompt: str) -> str:
        return f"""
You are a financial evidence extraction component.

Extract only facts explicitly supported by the supplied evidence.

Never decide affordability.
Never decide whether a payment is safe.
Never invent missing information.

Return JSON only:

{{
  "facts": [
    {{
      "fact_type": "amount|date|status|description|income|expense|payment|refund|cancellation|amendment|other",
      "value": "concise value",
      "confidence": 0.0,
      "related_event_id": "event_id or empty"
    }}
  ]
}}

Maximum 6 facts.

Evidence:
{prompt}
""".strip()

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = (text or "").strip()

        if text.startswith("```"):
            lines = text.splitlines()

            if lines and lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines).strip()

        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else {"facts": []}
        except json.JSONDecodeError:
            first = text.find("{")
            last = text.rfind("}")

            if first >= 0 and last > first:
                try:
                    value = json.loads(text[first:last + 1])
                    return (
                        value
                        if isinstance(value, dict)
                        else {"facts": []}
                    )
                except json.JSONDecodeError:
                    pass

        return {"facts": []}

    def _build_input(
        self,
        prompt: str,
        images: Iterable[Path],
    ):
        content = [
            {
                "type": "text",
                "text": self._prompt(prompt),
            }
        ]

        for image_path in images:
            image_path = Path(image_path)

            if not image_path.exists():
                continue

            mime_type = "image/png"

            if image_path.suffix.lower() in {
                ".jpg",
                ".jpeg",
            }:
                mime_type = "image/jpeg"

            # Interactions API supports multimodal input. The SDK's
            # convenience APIs may differ by installed version, so keep
            # image loading isolated here.
            content.append(
                {
                    "type": "image",
                    "mime_type": mime_type,
                    "data": image_path.read_bytes(),
                }
            )

        return content

    def extract(
        self,
        prompt: str,
        images: Iterable[Path] = (),
    ) -> GeminiResult:

        content = self._build_input(
            prompt,
            images,
        )

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                interaction = self.client.interactions.create(
                    model=self.model,
                    input=content,
                )

                text = interaction.output_text or ""
                data = self._parse_json(text)

                usage = getattr(
                    interaction,
                    "usage",
                    None,
                )

                input_tokens = int(
                    getattr(
                        usage,
                        "total_input_tokens",
                        0,
                    )
                    or 0
                )

                output_tokens = int(
                    getattr(
                        usage,
                        "total_output_tokens",
                        0,
                    )
                    or 0
                )

                total_tokens = int(
                    getattr(
                        usage,
                        "total_tokens",
                        0,
                    )
                    or 0
                )

                # Interactions currently exposes aggregate usage in the
                # response. Cached-token accounting may not be present in
                # every SDK response.
                cached_tokens = max(
                    total_tokens
                    - input_tokens
                    - output_tokens,
                    0,
                )

                facts = tuple(
                    fact
                    for fact in data.get("facts", [])
                    if isinstance(fact, dict)
                )

                return GeminiResult(
                    facts=facts,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=cached_tokens,
                    attempts=attempt,
                )

            except Exception as exc:
                last_error = exc

                if attempt >= self.max_retries:
                    break

                delay = min(
                    8.0,
                    (2 ** (attempt - 1))
                    + random.random(),
                )

                time.sleep(delay)

        raise RuntimeError(
            f"Gemini Interactions request failed "
            f"after {self.max_retries} attempts."
        ) from last_error
