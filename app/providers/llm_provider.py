from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

from ..config import load_config

Message = dict[str, object]

class LlmProvider:
    """LLM-backed metadata generator using a chat completions API."""

    TAG_INFERENCE_FIELDS: list[tuple[str, str]] = [
        ("PrimaryType", "tag_inference_primary_type"),
        ("Mode", "tag_inference_mode"),
        ("Romance", "tag_inference_romance"),
        ("Reader", "tag_inference_reader"),
        ("Setting", "tag_inference_setting"),
    ]

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 45.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "").strip()
        self.model = (model or os.getenv("LLM_MODEL") or "").strip()
        self.timeout = timeout
        self._prompt_dir = Path(__file__).resolve().parent / "prompts"

    def _build_messages(self, system_prompt_name: str, user_content: str) -> list[Message]:
        """Build a basic system+user message list for chat completions."""
        messages: list[Message] = []
        system_prompt = self._load_system_prompt(system_prompt_name)
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_content})
        return messages

    def _chat_payload(
        self,
        messages: list[Message],
        response_schema: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Create the chat completions payload, with optional JSON schema enforcement."""
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 512,
        }
        if response_schema:
            payload["response_format"] = response_schema
        return payload

    def _load_system_prompt(self, name: str) -> str | None:
        """Load a system prompt from the prompts directory."""
        path = self._prompt_dir / f"{name}.txt"
        if not path.is_file():
            return None
        content = path.read_text(encoding="utf-8").strip()
        return content or None

    def _load_response_schema(self, name: str) -> dict[str, object] | None:
        """Load a JSON schema file and convert it into response_format shape."""
        path = self._prompt_dir / f"{name}.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"Schema {name} invalid.") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=500, detail=f"Schema {name} invalid.")
        schema_name = payload.get("name") or name
        schema = payload.get("schema")
        if not isinstance(schema_name, str) or not schema_name.strip():
            raise HTTPException(status_code=500, detail=f"Schema {name} missing name.")
        if not isinstance(schema, dict):
            raise HTTPException(status_code=500, detail=f"Schema {name} missing schema.")
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        }

    def _require_schema(self, name: str) -> dict[str, object]:
        """Return a loaded schema or raise if missing."""
        response_schema = self._load_response_schema(name)
        if response_schema is None:
            raise HTTPException(status_code=500, detail=f"{name} schema not found.")
        return response_schema

    def _require_config(self) -> None:
        """Ensure required LLM configuration is present."""
        if not self.base_url:
            raise HTTPException(status_code=500, detail="LLM_BASE_URL or LLM_MODEL not configured.")
        config_model = load_config().llm_model
        if config_model:
            self.model = config_model
        if not self.model:
            raise HTTPException(status_code=500, detail="LLM_BASE_URL or LLM_MODEL not configured.")

    def _post_chat(self, payload: dict[str, object]) -> dict[str, object]:
        """POST a chat completion request and return the parsed JSON body."""
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
        """Return the first choice from a chat completion response."""
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=502, detail="LLM response missing choices.")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise HTTPException(status_code=502, detail="LLM response malformed.")
        return choice

    def _choice_content(self, choice: dict[str, object]) -> object | None:
        """Return the raw content payload for a choice."""
        if "content" in choice:
            return choice.get("content")
        message = choice.get("message")
        if isinstance(message, dict):
            return message.get("content")
        return None

    def _extract_reasoning(self, choice: dict[str, object]) -> str | None:
        """Extract reasoning from known response fields, if present."""
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
        """Extract and validate plain-text content."""
        choice = self._extract_choice(body)
        content = self._choice_content(choice)
        if not isinstance(content, str):
            raise HTTPException(status_code=502, detail="LLM response content invalid.")
        cleaned = content.strip()
        if not cleaned:
            raise HTTPException(status_code=502, detail=empty_detail)
        return cleaned

    def _parse_json_content(self, content: object, empty_detail: str) -> dict[str, object]:
        """Parse a JSON object from string or dict content."""
        if isinstance(content, dict):
            parsed = content
        elif isinstance(content, str):
            cleaned = content.strip()
            if not cleaned:
                raise HTTPException(status_code=502, detail=empty_detail)
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=502, detail="LLM response JSON invalid.") from exc
        else:
            raise HTTPException(status_code=502, detail="LLM response content invalid.")
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=502, detail="LLM response JSON must be an object.")
        return parsed

    def _extract_json_content(self, body: dict[str, object], empty_detail: str) -> dict[str, object]:
        """Extract JSON content without reasoning."""
        choice = self._extract_choice(body)
        content = self._choice_content(choice)
        return self._parse_json_content(content, empty_detail)

    def _extract_json_content_with_reasoning(
        self,
        body: dict[str, object],
        empty_detail: str,
    ) -> tuple[dict[str, object], str | None]:
        """Extract JSON content and a reasoning string if available."""
        choice = self._extract_choice(body)
        content = self._choice_content(choice)
        parsed = self._parse_json_content(content, empty_detail)
        reasoning = None
        raw_reasoning = parsed.get("reasoning")
        if isinstance(raw_reasoning, str) and raw_reasoning.strip():
            reasoning = raw_reasoning.strip()
        else:
            reasoning = self._extract_reasoning(choice)
        return parsed, reasoning

    def _extract_content_with_reasoning(
        self,
        body: dict[str, object],
        empty_detail: str,
    ) -> tuple[str, str | None]:
        """Extract plain-text content with optional reasoning."""
        choice = self._extract_choice(body)
        content = self._choice_content(choice)
        if not isinstance(content, str):
            raise HTTPException(status_code=502, detail="LLM response content invalid.")
        cleaned = content.strip()
        if not cleaned:
            raise HTTPException(status_code=502, detail=empty_detail)
        return cleaned, self._extract_reasoning(choice)

    def _request(
        self,
        *,
        system_prompt_name: str,
        user_content: str,
        schema_name: str | None,
    ) -> dict[str, object]:
        """Send a request for a prompt, optionally enforcing a response schema."""
        messages = self._build_messages(system_prompt_name, user_content)
        response_schema = self._require_schema(schema_name) if schema_name else None
        return self._post_chat(self._chat_payload(messages, response_schema=response_schema))

    def _text_result(
        self,
        body: dict[str, object],
        *,
        include_reasoning: bool,
        empty_detail: str,
    ) -> tuple[str, str | None]:
        """Parse a text response with optional reasoning."""
        if include_reasoning:
            return self._extract_content_with_reasoning(body, empty_detail)
        return self._extract_content(body, empty_detail), None

    def _json_result(
        self,
        body: dict[str, object],
        *,
        include_reasoning: bool,
        empty_detail: str,
    ) -> tuple[dict[str, object], str | None]:
        """Parse a JSON response with optional reasoning."""
        if include_reasoning:
            return self._extract_json_content_with_reasoning(body, empty_detail)
        return self._extract_json_content(body, empty_detail), None

    def _parse_tag_json(self, cleaned: str) -> list[str]:
        """Parse tag mappings from a JSON string payload."""
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="LLM tag JSON invalid.") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=502, detail="LLM tag JSON must be an object.")
        return self._parse_tag_mapping(parsed)

    def _parse_tag_mapping(self, parsed: dict[str, object]) -> list[str]:
        """Normalize a tag mapping dict into a flat list of tag strings."""
        tags: list[str] = []
        for key, value in parsed.items():
            key_text = str(key).strip()
            if key_text.lower() == "reasoning":
                continue
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

    def _coerce_tag_value(self, field: str, value: object) -> object:
        """Normalize a tag inference value for storage."""
        if field == "Romance":
            if isinstance(value, (int, float)):
                numeric = float(value)
            elif isinstance(value, str):
                try:
                    numeric = float(value.strip())
                except ValueError as exc:
                    raise HTTPException(
                        status_code=502,
                        detail="LLM tag JSON invalid.",
                    ) from exc
            else:
                raise HTTPException(status_code=502, detail="LLM tag JSON invalid.")
            return max(0.0, min(1.0, numeric))
        if value is None:
            raise HTTPException(status_code=502, detail="LLM tag JSON invalid.")
        if not isinstance(value, str):
            value = str(value)
        cleaned = value.strip()
        if not cleaned:
            raise HTTPException(status_code=502, detail="LLM tag JSON invalid.")
        return cleaned

    def get_tag_inference_fields(self) -> list[tuple[str, str]]:
        """Return the tag inference field/prompt pairs."""
        return list(self.TAG_INFERENCE_FIELDS)

    def tag_inference_field(
        self,
        book_description: str,
        *,
        field: str,
        prompt_name: str,
        include_reasoning: bool = False,
    ) -> tuple[object, str | None]:
        """Infer a single tag field from a book description."""
        self._require_config()
        raw_description = book_description.strip() or "No description provided"
        body = self._request(
            system_prompt_name=prompt_name,
            user_content=raw_description,
            schema_name=None,
        )
        choice = self._extract_choice(body)
        parsed = self._extract_json_content(body, "LLM returned empty tag JSON.")
        value = self._coerce_tag_value(field, parsed.get(field))
        reasoning = None
        if include_reasoning:
            reasoning = self._extract_reasoning(choice)
        return value, reasoning

    def tag_inference_split(
        self,
        book_description: str,
        include_reasoning: bool = False,
    ) -> tuple[list[str], list[tuple[str, str | None]]]:
        """Infer tags by running separate prompts per field."""
        tag_mapping: dict[str, object] = {}
        steps: list[tuple[str, str | None]] = []
        for field, prompt_name in self.TAG_INFERENCE_FIELDS:
            value, reasoning = self.tag_inference_field(
                book_description,
                field=field,
                prompt_name=prompt_name,
                include_reasoning=include_reasoning,
            )
            tag_mapping[field] = value
            steps.append((f"tag_inference_{field.lower()}", reasoning))
        return self._parse_tag_mapping(tag_mapping), steps

    def _clean_description_text(
        self,
        raw_description: str,
        *,
        include_reasoning: bool,
    ) -> tuple[str, str | None]:
        """Run the clean_description prompt with plain-text output."""
        body = self._request(
            system_prompt_name="clean_description",
            user_content=raw_description,
            schema_name=None,
        )
        return self._text_result(
            body,
            include_reasoning=include_reasoning,
            empty_detail="LLM returned empty description.",
        )

    def _clean_description_json(
        self,
        raw_description: str,
        *,
        include_reasoning: bool,
    ) -> tuple[str, str | None]:
        """Run the clean_description prompt with schema-enforced JSON output."""
        body = self._request(
            system_prompt_name="clean_description",
            user_content=raw_description,
            schema_name="BookDescription",
        )
        parsed, reasoning = self._json_result(
            body,
            include_reasoning=include_reasoning,
            empty_detail="LLM returned empty description.",
        )
        content = parsed.get("content")
        if not isinstance(content, str):
            raise HTTPException(status_code=502, detail="LLM response content invalid.")
        cleaned = content.strip()
        if not cleaned:
            raise HTTPException(status_code=502, detail="LLM returned empty description.")
        return cleaned, reasoning

    def _tag_inference_text(
        self,
        raw_description: str,
        *,
        include_reasoning: bool,
    ) -> tuple[list[str], str | None]:
        """Run tag inference with plain-text JSON output."""
        body = self._request(
            system_prompt_name="tag_inference",
            user_content=raw_description,
            schema_name=None,
        )
        cleaned, reasoning = self._text_result(
            body,
            include_reasoning=include_reasoning,
            empty_detail="LLM returned empty tag JSON.",
        )
        return self._parse_tag_json(cleaned), reasoning

    def _tag_inference_json(
        self,
        raw_description: str,
        *,
        include_reasoning: bool,
    ) -> tuple[list[str], str | None]:
        """Run tag inference with schema-enforced JSON output."""
        body = self._request(
            system_prompt_name="tag_inference",
            user_content=raw_description,
            schema_name="BookClassification",
        )
        parsed, reasoning = self._json_result(
            body,
            include_reasoning=include_reasoning,
            empty_detail="LLM returned empty tag JSON.",
        )
        return self._parse_tag_mapping(parsed), reasoning

    def clean_description(
        self,
        description: str,
        include_reasoning: bool = False,
        include_schema: bool = False,
    ) -> tuple[str, str | None]:
        """Request a cleaned description (and optional reasoning) from the configured LLM endpoint."""
        self._require_config()
        raw_description = description.strip() or "No description provided"
        if include_schema:
            return self._clean_description_json(
                raw_description,
                include_reasoning=include_reasoning,
            )
        return self._clean_description_text(
            raw_description,
            include_reasoning=include_reasoning,
        )

    def tag_inference(
        self,
        book_description: str,
        include_reasoning: bool = False,
        include_schema: bool = False,
    ) -> tuple[list[str], str | None]:
        """Infer normalized tags (and optional reasoning) from a book description via the LLM."""
        self._require_config()
        raw_description = book_description.strip() or "No description provided"
        if include_schema:
            return self._tag_inference_json(
                raw_description,
                include_reasoning=include_reasoning,
            )
        return self._tag_inference_text(
            raw_description,
            include_reasoning=include_reasoning,
        )
