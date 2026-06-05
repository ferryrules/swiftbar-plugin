"""Ollama HTTP client for Rewind synth — works against either runtime.

Two runtimes, one client:

- **Local Ollama** (default when OLLAMA_API_KEY is unset): hits
  http://127.0.0.1:11434, no auth. Install once: `brew install ollama &&
  brew services start ollama && ollama pull llama3.2:3b`. Nothing leaves
  the box.

- **Ollama Cloud** (auto-selected when OLLAMA_API_KEY is set): hits
  https://ollama.com/api/chat with a Bearer token. No local install
  needed, access to bigger hosted models (gpt-oss:120b, gpt-oss:20b).
  Metadata-only payload still applies via privacy.build_llm_payload().

Falls back to the template synth on any error so the plugin is never
blocked on the LLM being up.
"""

import json
import os
import urllib.error
import urllib.request

DEFAULT_LOCAL_URL = "http://127.0.0.1:11434"
DEFAULT_CLOUD_URL = "https://ollama.com"
DEFAULT_LOCAL_MODEL = "llama3.2:3b"
DEFAULT_CLOUD_MODEL = "gpt-oss:120b"
DEFAULT_TIMEOUT = 15


def _api_key():
    return os.environ.get("OLLAMA_API_KEY", "").strip()


def is_cloud():
    return bool(_api_key())


def base_url():
    explicit = os.environ.get("REWIND_OLLAMA_URL")
    if explicit:
        return explicit.rstrip("/")
    return (DEFAULT_CLOUD_URL if is_cloud() else DEFAULT_LOCAL_URL).rstrip("/")


def model():
    explicit = os.environ.get("REWIND_OLLAMA_MODEL")
    if explicit:
        return explicit
    return DEFAULT_CLOUD_MODEL if is_cloud() else DEFAULT_LOCAL_MODEL


def runtime_label():
    """Short string for logging / menu UI: 'ollama (cloud:gpt-oss:120b)' etc."""
    return f"ollama ({'cloud' if is_cloud() else 'local'}:{model()})"


def _headers():
    h = {"content-type": "application/json"}
    key = _api_key()
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def is_running(timeout=2.0):
    """Cheap liveness check — short-circuits synth when Ollama isn't reachable."""
    try:
        req = urllib.request.Request(f"{base_url()}/api/tags", headers=_headers())
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


def chat_json(prompt, system=None, timeout=DEFAULT_TIMEOUT, max_tokens=300):
    """Send `prompt` to Ollama (local or cloud) in JSON mode; return parsed dict or None.

    `format: "json"` makes Ollama emit a single valid JSON object — no regex
    extraction needed. Returns None on any failure (server down, model not
    available, JSON parse error, timeout, auth rejected).
    """
    body = {
        "model": model(),
        "messages": (
            ([{"role": "system", "content": system}] if system else [])
            + [{"role": "user", "content": prompt}]
        ),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": max_tokens},
    }
    req = urllib.request.Request(
        f"{base_url()}/api/chat",
        data=json.dumps(body).encode(),
        headers=_headers(),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    content = (data.get("message") or {}).get("content") or ""
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None
