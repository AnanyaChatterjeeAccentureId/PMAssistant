from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from config import API_KEY, DEPLOYMENT, ENDPOINT


class GenAIService:
    """Uses Azure OpenAI for intent interpretation only."""

    _SYSTEM_PROMPT = """Classify the staffing request and return JSON only:
{"intent":"resource_search"} or {"intent":"team_composition"}.
Use team_composition when the user asks to build, create, compose, form, or assemble
a team, or specifies multiple role quantities. Use resource_search for an individual
resource/profile search. Never return any other intent."""

    def __init__(self) -> None:
        try:
            from openai import AzureOpenAI
        except ModuleNotFoundError as error:
            raise ValueError(
                "The openai package is not installed in the active Python "
                "environment. Install it with: python -m pip install openai"
            ) from error

        if not ENDPOINT or not API_KEY or not DEPLOYMENT:
            raise ValueError(
                "Azure OpenAI configuration is incomplete. "
                "Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and "
                "AZURE_OPENAI_DEPLOYMENT."
            )
        endpoint = urlsplit(ENDPOINT)
        azure_endpoint = urlunsplit(
            (endpoint.scheme, endpoint.netloc, "", "", "")
        ).rstrip("/")
        self._client = AzureOpenAI(
            api_key=API_KEY,
            azure_endpoint=azure_endpoint,
            api_version="2024-10-21",
        )

    def detect_intent(self, prompt: str) -> str | None:
        response = self._client.chat.completions.create(
            model=DEPLOYMENT,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            return None
        payload: Any = json.loads(content)
        intent = payload.get("intent") if isinstance(payload, dict) else None
        return intent if intent in {"resource_search", "team_composition"} else None

    @classmethod
    def try_detect_intent(cls, prompt: str) -> str | None:
        try:
            from openai import OpenAIError
        except ModuleNotFoundError:
            return None
        try:
            return cls().detect_intent(prompt)
        except (ValueError, TypeError, json.JSONDecodeError):
            return None
        except OpenAIError:
            return None
