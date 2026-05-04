"""src/ai/llm_providers.py — Multi-provider LLM client.

Supports:
- Ollama (local, default)
- OpenAI (GPT-4, GPT-4o, GPT-3.5)
- Anthropic (Claude 3 Opus/Sonnet/Haiku)
- Groq (fast inference: llama3, mixtral)
- OpenRouter / Together.ai (any model)

Configured via .env or API.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    provider: str           # "ollama", "openai", "anthropic", "groq", "openrouter", "together"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    max_tokens: int = 2048
    temperature: float = 0.1

    @property
    def is_local(self) -> bool:
        return self.provider == "ollama"


class MultiLLMClient:
    """Unified client for multiple LLM providers.

    Usage:
        client = MultiLLMClient()
        client.add_provider("openai", api_key="sk-...", model="gpt-4o")
        client.add_provider("anthropic", api_key="sk-ant-...", model="claude-3-opus")
        answer = client.generate("ollama", prompt="Hello")   # local
        answer = client.generate("openai", prompt="Hello")   # cloud
    """

    PROVIDER_DEFAULTS = {
        "ollama":    {"base_url": "http://localhost:11434", "model": "qwen2.5:latest"},
        "openai":    {"base_url": "https://api.openai.com/v1", "model": "gpt-4o"},
        "anthropic": {"base_url": "https://api.anthropic.com/v1", "model": "claude-3-opus-20240229"},
        "groq":      {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
        "deepseek":  {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
        "openrouter":{"base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-4o"},
        "together":  {"base_url": "https://api.together.xyz/v1", "model": "meta-llama/Llama-3.3-70B-Instruct"},
    }

    def __init__(self):
        self._providers: Dict[str, ProviderConfig] = {}
        # Auto-load from env
        self._load_from_env()

    def _load_from_env(self):
        """Load providers from environment variables."""
        # Ollama (always available as fallback)
        ollama_host = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("LLM_MODEL", "qwen2.5:latest")
        self.add_provider("ollama", base_url=ollama_host, model=ollama_model)

        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            self.add_provider("openai",
                api_key=os.getenv("OPENAI_API_KEY"),
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            )

        # Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            self.add_provider("anthropic",
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                model=os.getenv("ANTHROPIC_MODEL", "claude-3-opus-20240229"),
            )

        # Groq
        if os.getenv("GROQ_API_KEY"):
            self.add_provider("groq",
                api_key=os.getenv("GROQ_API_KEY"),
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            )

        # DeepSeek
        if os.getenv("DEEPSEEK_API_KEY"):
            self.add_provider("deepseek",
                api_key=os.getenv("sk-c15c7009c24147489cf10c3d7d58365a"),
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            )

        # OpenRouter
        if os.getenv("OPENROUTER_API_KEY"):
            self.add_provider("openrouter",
                api_key=os.getenv("OPENROUTER_API_KEY"),
                model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o"),
            )

        # Together.ai
        if os.getenv("TOGETHER_API_KEY"):
            self.add_provider("together",
                api_key=os.getenv("TOGETHER_API_KEY"),
                model=os.getenv("TOGETHER_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
            )

    def add_provider(self, name: str, **kwargs):
        """Add or update a provider configuration."""
        defaults = self.PROVIDER_DEFAULTS.get(name, {})
        config = ProviderConfig(
            provider=name,
            base_url=kwargs.get("base_url", defaults.get("base_url", "")),
            model=kwargs.get("model", defaults.get("model", "")),
            api_key=kwargs.get("api_key", ""),
            max_tokens=kwargs.get("max_tokens", 2048),
            temperature=kwargs.get("temperature", 0.1),
        )
        self._providers[name] = config

    def remove_provider(self, name: str):
        self._providers.pop(name, None)

    def list_providers(self) -> List[Dict[str, str]]:
        return [
            {"name": name, "model": c.model, "is_local": c.is_local}
            for name, c in self._providers.items()
        ]

    def get_provider(self, name: str = "ollama") -> Optional[ProviderConfig]:
        return self._providers.get(name)

    def is_available(self, provider: str = "ollama") -> bool:
        cfg = self._providers.get(provider)
        if not cfg:
            return False
        if cfg.is_local:
            try:
                r = requests.get(f"{cfg.base_url}/api/tags", timeout=3)
                return r.status_code == 200
            except Exception:
                return False
        return bool(cfg.api_key)

    def chat(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Send a chat completion request to the specified provider."""
        cfg = self._providers.get(provider)
        if not cfg:
            raise ValueError(f"Unknown provider: {provider}. Available: {list(self._providers)}")

        if cfg.is_local:
            return self._chat_ollama(cfg, messages, system_prompt, temperature, max_tokens)

        if cfg.provider == "anthropic":
            return self._chat_anthropic(cfg, messages, system_prompt, temperature, max_tokens)

        # OpenAI-compatible API (OpenAI, Groq, OpenRouter, Together)
        return self._chat_openai_compatible(cfg, messages, system_prompt, temperature, max_tokens)

    def generate(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """Shortcut: single-turn generation."""
        return self.chat(
            provider=provider,
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # ── Provider-specific implementations ────────────────────────────

    def _chat_ollama(self, cfg, messages, system_prompt, temperature, max_tokens):
        payload = {
            "model": cfg.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature or cfg.temperature,
                "num_predict": max_tokens or cfg.max_tokens,
            },
        }
        if system_prompt:
            payload["messages"] = [{"role": "system", "content": system_prompt}] + messages

        r = requests.post(f"{cfg.base_url}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()

    def _chat_openai_compatible(self, cfg, messages, system_prompt, temperature, max_tokens):
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }
        msgs = messages
        if system_prompt:
            msgs = [{"role": "system", "content": system_prompt}] + msgs

        payload = {
            "model": cfg.model,
            "messages": msgs,
            "temperature": temperature or cfg.temperature,
            "max_tokens": max_tokens or cfg.max_tokens,
        }

        # Groq needs extra headers
        if cfg.provider == "groq":
            payload.pop("max_tokens", None)
            payload["max_completion_tokens"] = max_tokens or cfg.max_tokens

        r = requests.post(
            f"{cfg.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

    def _chat_anthropic(self, cfg, messages, system_prompt, temperature, max_tokens):
        headers = {
            "x-api-key": cfg.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": cfg.model,
            "messages": messages,
            "max_tokens": max_tokens or cfg.max_tokens,
            "temperature": temperature or cfg.temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        r = requests.post(
            f"{cfg.base_url}/messages",
            headers=headers,
            json=payload,
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("content", [{}])[0].get("text", "").strip()
