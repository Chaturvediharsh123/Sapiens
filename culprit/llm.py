"""Local model client (Ollama). Everything runs on this machine: no hosted model APIs.

- temperature 0 + fixed seed, so repeated runs give the same answers
- structured JSON output validated with pydantic, with retries on bad output
- code answers are taken from a ```python block
- token counts from Ollama are kept for the tokens/sec metric
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import TypeVar

import requests
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if not DEFAULT_HOST.startswith("http"):
    DEFAULT_HOST = "http://" + DEFAULT_HOST


class LLMError(RuntimeError):
    pass


@dataclass
class LLMStats:
    calls: int = 0
    retries: int = 0
    eval_tokens: int = 0
    eval_seconds: float = 0.0
    prompt_tokens: int = 0
    wall_seconds: float = 0.0
    by_purpose: dict = field(default_factory=dict)

    @property
    def tokens_per_sec(self) -> float:
        return self.eval_tokens / self.eval_seconds if self.eval_seconds else 0.0


def list_models(host: str = DEFAULT_HOST) -> list[dict]:
    r = requests.get(f"{host}/api/tags", timeout=5)
    r.raise_for_status()
    return r.json().get("models", [])


def resolve_model(requested: str | None, host: str = DEFAULT_HOST) -> str:
    """Use the requested model, else CULPRIT_MODEL, else the smallest installed Gemma 4."""
    name = requested or os.environ.get("CULPRIT_MODEL")
    try:
        models = list_models(host)
    except requests.RequestException as exc:
        raise LLMError(f"Cannot reach Ollama at {host}. Start it with `ollama serve`. ({exc})")
    names = [m["name"] for m in models]
    if name:
        if name in names or f"{name}:latest" in names:
            return name
        raise LLMError(f"Model '{name}' is not installed. Installed: {', '.join(names) or 'none'}. "
                       f"Run `ollama pull {name}`.")
    gemma = sorted((m for m in models if m["name"].startswith("gemma4")), key=lambda m: m.get("size", 0))
    if gemma:
        return gemma[0]["name"]
    raise LLMError("No Gemma 4 model installed. Pull one with `ollama pull gemma4` "
                   "(pick the smallest size that fits your RAM) or pass --model.")


def extract_code(text: str) -> str | None:
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, flags=re.S)
    if blocks:
        return max(blocks, key=len).strip("\n") + "\n"
    stripped = text.strip()
    if stripped.startswith(("def ", "import ", "from ", "class ", "@")):
        return stripped + "\n"
    return None


class OllamaLLM:
    def __init__(self, model: str, host: str = DEFAULT_HOST, num_ctx: int = 4096,
                 seed: int = 42, timeout: int = 600, log=None):
        self.model = model
        self.host = host.rstrip("/")
        self.num_ctx = num_ctx
        self.seed = seed
        self.timeout = timeout
        self.stats = LLMStats()
        self.log = log or (lambda msg: None)

    # -- raw call ---------------------------------------------------------------
    def _chat(self, messages: list[dict], fmt=None, purpose: str = "") -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": 0, "seed": self.seed, "num_ctx": self.num_ctx},
        }
        if fmt is not None:
            body["format"] = fmt
        t0 = time.time()
        try:
            r = requests.post(f"{self.host}/api/chat", json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMError(f"Ollama request failed: {exc}")
        if r.status_code >= 400 and fmt not in (None, "json"):
            body["format"] = "json"          # older Ollama: no JSON-schema support
            r = requests.post(f"{self.host}/api/chat", json=body, timeout=self.timeout)
        if r.status_code >= 400:
            raise LLMError(f"Ollama error {r.status_code}: {r.text[:300]}")
        data = r.json()
        s = self.stats
        s.calls += 1
        s.eval_tokens += data.get("eval_count", 0)
        s.eval_seconds += data.get("eval_duration", 0) / 1e9
        s.prompt_tokens += data.get("prompt_eval_count", 0)
        s.wall_seconds += time.time() - t0
        s.by_purpose[purpose] = s.by_purpose.get(purpose, 0) + 1
        return data.get("message", {}).get("content", "")

    # -- structured JSON -------------------------------------------------------------
    def json(self, system: str, user: str, schema: type[T], purpose: str = "", retries: int = 3) -> T:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_err = ""
        for attempt in range(retries):
            text = self._chat(messages, fmt=schema.model_json_schema(), purpose=purpose)
            try:
                return schema.model_validate(json.loads(text))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_err = str(exc)[:500]
                self.stats.retries += 1
                messages += [{"role": "assistant", "content": text},
                             {"role": "user", "content": f"That was not valid JSON for the schema: {last_err}. "
                                                         "Reply again with only the JSON object."}]
        raise LLMError(f"model never returned valid JSON for {purpose}: {last_err}")

    # -- code answers ---------------------------------------------------------------
    def code(self, system: str, user: str, purpose: str = "", history: list[dict] | None = None) -> str:
        messages = [{"role": "system", "content": system}, *(history or []),
                    {"role": "user", "content": user}]
        for _ in range(2):
            text = self._chat(messages, purpose=purpose)
            code = extract_code(text)
            if code:
                return code
            self.stats.retries += 1
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": "Reply with only one ```python code block."}]
        raise LLMError(f"model did not return a code block for {purpose}")
