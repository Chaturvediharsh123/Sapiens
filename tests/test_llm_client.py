"""Tests for the Ollama client against a tiny local server that speaks Ollama's /api/chat format."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from culprit.llm import OllamaLLM, extract_code, resolve_model, usable_models  # noqa: E402
from culprit.locate import Keywords  # noqa: E402

REPLIES: list[str] = []
SEEN: list[dict] = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send({"models": [{"name": "gemma4:big", "size": 9_000},
                               {"name": "gemma4:small", "size": 2_000},
                               {"name": "llama3:8b", "size": 5_000}]})

    def do_POST(self):
        SEEN.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self._send({"message": {"role": "assistant", "content": REPLIES.pop(0)},
                    "eval_count": 50, "eval_duration": 2_000_000_000, "prompt_eval_count": 100})


@pytest.fixture(scope="module")
def host():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_picks_smallest_gemma(host):
    assert resolve_model(None, host) == "gemma4:small"


def test_json_retries_until_valid_and_is_deterministic(host):
    SEEN.clear()
    REPLIES[:] = ["not json at all", '{"keywords": ["email", "signup"]}']
    llm = OllamaLLM("gemma4:small", host)
    out = llm.json("sys", "user", Keywords, purpose="keywords")
    assert out.keywords == ["email", "signup"]
    assert llm.stats.retries == 1 and llm.stats.calls == 2
    assert SEEN[0]["options"]["temperature"] == 0 and "seed" in SEEN[0]["options"]
    assert SEEN[0]["format"]["properties"]["keywords"]["type"] == "array"
    assert llm.stats.tokens_per_sec == pytest.approx(25.0)


def test_code_extraction(host):
    REPLIES[:] = ["Here you go:\n```python\ndef test_culprit_repro():\n    assert 1\n```\nDone."]
    llm = OllamaLLM("gemma4:small", host)
    assert llm.code("sys", "user", purpose="repro").startswith("def test_culprit_repro")
    assert extract_code("no code here") is None


def test_any_installed_chat_model_is_used_when_no_gemma4():
    models = [{"name": "nomic-embed-text:latest", "size": 274e6, "details": {"family": "nomic-bert"}},
              {"name": "tinyllama:latest", "size": 637e6},
              {"name": "llama3.1:70b", "size": 40e9},
              {"name": "mistral:7b", "size": 4.1e9},
              {"name": "qwen2.5-coder:3b", "size": 1.9e9}]
    ranked = [m["name"] for m in usable_models(models)]
    assert ranked[0] == "qwen2.5-coder:3b"
    assert "nomic-embed-text:latest" not in ranked
    assert ranked[-1] == "llama3.1:70b"


def test_thinking_text_is_removed(host):
    REPLIES[:] = ['<think>let me reason about this</think>{"keywords": ["tax"]}']
    out = OllamaLLM("gemma4:small", host).json("sys", "user", Keywords, purpose="keywords")
    assert out.keywords == ["tax"]
