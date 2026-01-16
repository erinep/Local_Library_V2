from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

Message = dict[str, object]

class LlmProvider:
    """LLM-backed metadata generator using a chat completions API."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "").strip()
        self.model = (model or os.getenv("LLM_MODEL") or "").strip()
        self.timeout = timeout
        self._prompt_dir = Path(__file__).resolve().parent / "prompts"

    def _build_messages(self, system_prompt_name: str, user_content: str) -> list[Message]:
        messages: list[Message] = []
        system_prompt = self._load_system_prompt(system_prompt_name)
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_content})
        return messages

    def _chat_payload(self, messages: list[Message]) -> dict[str, object]:
        return {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 512,
        }

    def _load_system_prompt(self, name: str) -> str | None:
        path = self._prompt_dir / f"{name}.txt"
        if not path.is_file():
            return None
        content = path.read_text(encoding="utf-8").strip()
        return content or None

    def _require_config(self) -> None:
        if not self.base_url or not self.model:
            raise HTTPException(status_code=500, detail="LLM_BASE_URL or LLM_MODEL not configured.")

    def _post_chat(self, payload: dict[str, object]) -> dict[str, object]:
        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except socket.timeout as exc:
            raise HTTPException(status_code=504, detail="LLM request timed out.") from exc
        except (HTTPError, URLError, ValueError) as exc:
            if isinstance(exc, URLError) and isinstance(exc.reason, socket.timeout):
                raise HTTPException(status_code=504, detail="LLM request timed out.") from exc
            raise HTTPException(status_code=502, detail="LLM request failed.") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=502, detail="LLM response malformed.")
        return body

    def _extract_choice(self, body: dict[str, object]) -> dict[str, object]:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=502, detail="LLM response missing choices.")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise HTTPException(status_code=502, detail="LLM response malformed.")
        return choice

    def _choice_content(self, choice: dict[str, object]) -> object | None:
        if "content" in choice:
            return choice.get("content")
        message = choice.get("message")
        if isinstance(message, dict):
            return message.get("content")
        return None

    def _extract_reasoning(self, choice: dict[str, object]) -> str | None:
        reasoning = choice.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning.strip()
        message = choice.get("message")
        if isinstance(message, dict):
            message_reasoning = message.get("reasoning")
            if isinstance(message_reasoning, str) and message_reasoning.strip():
                return message_reasoning.strip()
        content = choice.get("content")
        if isinstance(content, dict):
            content_reasoning = content.get("reasoning")
            if isinstance(content_reasoning, str) and content_reasoning.strip():
                return content_reasoning.strip()
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_reasoning = item.get("reasoning")
                if isinstance(item_reasoning, str) and item_reasoning.strip():
                    return item_reasoning.strip()
        return None

    def _extract_content(self, body: dict[str, object], empty_detail: str) -> str:
        choice = self._extract_choice(body)
        content = self._choice_content(choice)
        if not isinstance(content, str):
            raise HTTPException(status_code=502, detail="LLM response content invalid.")
        cleaned = content.strip()
        if not cleaned:
            raise HTTPException(status_code=502, detail=empty_detail)
        return cleaned

    def _extract_content_with_reasoning(
        self,
        body: dict[str, object],
        empty_detail: str,
    ) -> tuple[str, str | None]:
        choice = self._extract_choice(body)
        content = self._choice_content(choice)
        if not isinstance(content, str):
            raise HTTPException(status_code=502, detail="LLM response content invalid.")
        cleaned = content.strip()
        if not cleaned:
            raise HTTPException(status_code=502, detail=empty_detail)
        return cleaned, self._extract_reasoning(choice)

    def _parse_tag_json(self, cleaned: str) -> list[str]:
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="LLM tag JSON invalid.") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=502, detail="LLM tag JSON must be an object.")
        tags: list[str] = []
        for key, value in parsed.items():
            key_text = str(key).strip()
            if not key_text:
                continue
            if isinstance(value, list):
                for item in value:
                    value_text = str(item).strip()
                    if value_text:
                        tags.append(f"{key_text}:{value_text}")
                continue
            value_text = str(value).strip()
            if value_text:
                tags.append(f"{key_text}:{value_text}")
        return tags

    def clean_description(
        self,
        title: str,
        author: str,
        description: str,
        include_reasoning: bool = False,
    ) -> tuple[str, str | None]:
        """Request a cleaned description (and optional reasoning) from the configured LLM endpoint."""
        self._require_config()
        raw_title = title.strip() or "Unknown title"
        raw_author = author.strip() or "Unknown author"
        raw_description = description.strip() or "No description provided"
        user_content = f"{raw_title} | author: {raw_author} | description: {raw_description}"
        messages = self._build_messages("clean_description", user_content)
        body = self._post_chat(self._chat_payload(messages))
        if include_reasoning:
            return self._extract_content_with_reasoning(body, "LLM returned empty description.")
        return self._extract_content(body, "LLM returned empty description."), None

    def tag_inference(
        self,
        book_description: str,
        include_reasoning: bool = False,
    ) -> tuple[list[str], str | None]:
        """Infer normalized tags (and optional reasoning) from a book description via the LLM."""
        self._require_config()
        raw_description = book_description.strip() or "No description provided"
        messages = self._build_messages("tag_inference", raw_description)
        body = self._post_chat(self._chat_payload(messages))
        if include_reasoning:
            cleaned, reasoning = self._extract_content_with_reasoning(
                body,
                "LLM returned empty tag JSON.",
            )
            return self._parse_tag_json(cleaned), reasoning
        cleaned = self._extract_content(body, "LLM returned empty tag JSON.")
        return self._parse_tag_json(cleaned), None
