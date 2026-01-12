from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

class LlmProvider:
    """LLM-backed metadata generator using a chat completions API."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "").strip()
        self.model = (model or os.getenv("LLM_MODEL") or "").strip()
        self.timeout = timeout
        self._prompt_dir = Path(__file__).resolve().parent / "prompts"

    def _load_system_prompt(self, name: str) -> str | None:
        path = self._prompt_dir / f"{name}.txt"
        if not path.is_file():
            return None
        content = path.read_text(encoding="utf-8").strip()
        return content or None

    def get_description(self, title: str, author: str) -> str | None:
        """Request a short description from the configured LLM endpoint."""
        if not self.base_url or not self.model:
            raise HTTPException(status_code=500, detail="LLM_BASE_URL or LLM_MODEL not configured.")
        prompt_title = title.strip() or "Unknown title"
        prompt_author = author.strip() or "Unknown author"
        messages = []
        system_prompt = self._load_system_prompt("get_description")
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append(
            {
                "role": "user",
                "content": f"Title: {prompt_title} | Author: {prompt_author}",
            }
        )
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 512,
        }
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
        choices = body.get("choices") if isinstance(body, dict) else None
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=502, detail="LLM response missing choices.")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise HTTPException(status_code=502, detail="LLM response malformed.")
        content = choice.get("content")
        if content is None and isinstance(choice.get("message"), dict):
            content = choice["message"].get("content")
        if not isinstance(content, str):
            raise HTTPException(status_code=502, detail="LLM response content invalid.")
        cleaned = content.strip()
        if not cleaned:
            raise HTTPException(status_code=502, detail="LLM returned empty description.")
        return cleaned

    def clean_description(self, title: str, author: str, description: str) -> str | None:
        """Request a cleaned description from the configured LLM endpoint."""
        if not self.base_url or not self.model:
            raise HTTPException(status_code=500, detail="LLM_BASE_URL or LLM_MODEL not configured.")
        raw_title = title.strip() or "Unknown title"
        raw_author = author.strip() or "Unknown author"
        raw_description = description.strip() or "No description provided"
        messages = []
        system_prompt = self._load_system_prompt("clean_description")
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append(
            {
                "role": "user",
                "content": f"{raw_title} | author: {raw_author} | description: {raw_description}",
            }
        )
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 512,
        }
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
        choices = body.get("choices") if isinstance(body, dict) else None
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=502, detail="LLM response missing choices.")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise HTTPException(status_code=502, detail="LLM response malformed.")
        content = choice.get("content")
        if content is None and isinstance(choice.get("message"), dict):
            content = choice["message"].get("content")
        if not isinstance(content, str):
            raise HTTPException(status_code=502, detail="LLM response content invalid.")
        cleaned = content.strip()
        if not cleaned:
            raise HTTPException(status_code=502, detail="LLM returned empty description.")
        return cleaned

    def get_tags(self, result_id: str):
        """Placeholder for LLM-backed tag generation."""
        raise HTTPException(status_code=501, detail="LLM tag generation not implemented.")
