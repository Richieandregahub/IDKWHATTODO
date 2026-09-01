"""LLM clients: real (OpenAI-compatible / OpenRouter) + a free offline Demo client."""

import json
import random
import time

import requests

PROVIDER_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
}


class LLMError(Exception):
    pass


class LLMClient:
    """Streams chat completions from any OpenAI-compatible API."""

    def __init__(self, cfg):
        self.provider = cfg.get("provider", "openai")
        self.api_key = cfg.get("api_key", "")
        self.base_url = (cfg.get("base_url") or PROVIDER_URLS.get(self.provider, "")).rstrip("/")
        if not self.base_url:
            raise LLMError("No base_url configured for provider '%s'" % self.provider)

    def stream_chat(self, model, messages, temperature=0.7):
        """Yield text chunks as they arrive."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/Richieandregahub/IDKWHATTODO"
            headers["X-Title"] = "arena-cli"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=120,
            )
        except requests.RequestException as e:
            raise LLMError(f"Network error: {e}") from e
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", {}).get("message", resp.text[:300])
            except Exception:
                err = resp.text[:300]
            raise LLMError(f"API error {resp.status_code}: {err}")

        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace")
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0].get("delta", {}).get("content")
                if delta:
                    yield delta
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

    def chat(self, model, messages, temperature=0.7):
        return "".join(self.stream_chat(model, messages, temperature))


# ---------------------------------------------------------------------------
# Demo mode - no API key needed, fake "models" with personalities
# ---------------------------------------------------------------------------

DEMO_MODELS = [
    "demo/gpt-fake-5",
    "demo/claude-parody-4",
    "demo/gemini-imitation-pro",
    "demo/llama-cosplay-70b",
    "demo/deepfake-seek-v3",
    "demo/qwen-not-really-72b",
]

_DEMO_STYLES = {
    "demo/gpt-fake-5": "Certainly! Here's my take: {topic}. In summary, it depends on the context, but I'd recommend starting simple and iterating from there.",
    "demo/claude-parody-4": "Great question. Let me think about \"{topic}\" carefully.\n\n1. First, consider the fundamentals.\n2. Then weigh the trade-offs.\n3. Finally, pick what fits your situation.\n\nHappy to go deeper on any of these!",
    "demo/gemini-imitation-pro": "Here's a quick breakdown of {topic}:\n\n* Key idea: keep it simple\n* Pro tip: measure before optimizing\n* Bottom line: you got this",
    "demo/llama-cosplay-70b": "Alright, {topic} - love it. Short version: just start, break it into tiny steps, and don't overthink it. The long version is the same but with more coffee.",
    "demo/deepfake-seek-v3": "Analyzing: {topic}\n\nStep 1: understand the problem.\nStep 2: sketch a minimal solution.\nStep 3: test, then improve.\n\nConclusion: iterative beats perfect.",
    "demo/qwen-not-really-72b": "Regarding {topic}: the most practical path is usually the boring one. Write it down, try the smallest version, and refine. Boring is underrated.",
}


class DemoClient:
    """Offline pretend-LLM so the app works with zero API keys."""

    provider = "demo"

    def stream_chat(self, model, messages, temperature=0.7):
        user_msg = ""
        for m in reversed(messages):
            if m["role"] == "user":
                user_msg = m["content"]
                break
        topic = user_msg.strip().rstrip("?.!") or "your question"
        if len(topic) > 60:
            topic = topic[:57] + "..."
        template = _DEMO_STYLES.get(model, "Here are my thoughts on {topic}. (demo mode)")
        text = template.format(topic=topic)
        text += "\n\n(demo mode - add an API key via Settings to talk to real models)"
        for word in text.split(" "):
            yield word + " "
            time.sleep(random.uniform(0.005, 0.03))

    def chat(self, model, messages, temperature=0.7):
        return "".join(self.stream_chat(model, messages, temperature))


def get_client(cfg):
    if cfg.get("provider") == "demo" or not cfg.get("api_key"):
        return DemoClient()
    return LLMClient(cfg)


def get_models(cfg):
    if cfg.get("provider") == "demo" or not cfg.get("api_key"):
        return list(DEMO_MODELS)
    return list(cfg.get("models") or [])
