"""src/ai/llm_client.py — Unified LLM client (Ollama local + cloud APIs)."""
import logging
import os
from typing import Any, Dict, List, Optional

import requests

from config.settings import DEFAULT_MODEL, OLLAMA_HOST

logger = logging.getLogger(__name__)


class LLMClient:
    """Client LLM unifié. Supporte Ollama (local) + APIs cloud.

    Usage:
        # Ollama local (par défaut)
        llm = LLMClient()

        # DeepSeek API
        llm = LLMClient(provider="deepseek")

        # OpenAI API
        llm = LLMClient(provider="openai", model="gpt-4o")

        # Via .env :
        #   LLM_PROVIDER=deepseek
        #   DEEPSEEK_API_KEY=sk-...
        # Puis : llm = LLMClient()  → détecte automatiquement
    """

    def __init__(
        self,
        model: str = None,
        host: str = None,
        provider: str = None,
    ):
        # Détection automatique depuis .env
        self.provider = provider or os.getenv("LLM_PROVIDER", "ollama")
        self.host = (host or OLLAMA_HOST).rstrip("/")

        # Modèle par défaut selon le provider
        _provider_defaults = {
            "ollama": DEFAULT_MODEL,
            "openai": "gpt-4o",
            "deepseek": "deepseek-chat",
            "anthropic": "claude-3-opus-20240229",
            "groq": "llama-3.3-70b-versatile",
            "openrouter": "openai/gpt-4o",
            "together": "meta-llama/Llama-3.3-70B-Instruct",
        }
        default_for_provider = _provider_defaults.get(self.provider, DEFAULT_MODEL)
        self.model = model or default_for_provider

        # Si provider n'est pas ollama, charger la config API
        if self.provider != "ollama":
            self._api_key = os.getenv(f"{self.provider.upper()}_API_KEY", "")
            # Override model from env si défini
            api_model = os.getenv(f"{self.provider.upper()}_MODEL", "")
            if api_model:
                self.model = api_model
            if model:
                self.model = model  # override explicite prime

            # Base URLs par provider
            self._base_urls = {
                "openai": "https://api.openai.com/v1",
                "deepseek": "https://api.deepseek.com/v1",
                "groq": "https://api.groq.com/openai/v1",
                "openrouter": "https://openrouter.ai/api/v1",
                "together": "https://api.together.xyz/v1",
            }

    # ── Disponibilité ────────────────────────────────────────────────

    def is_available(self) -> bool:
        if self.provider == "ollama":
            try:
                r = requests.get(f"{self.host}/api/tags", timeout=3)
                return r.status_code == 200
            except Exception:
                return False
        return bool(self._api_key)

    def list_models(self) -> List[str]:
        if self.provider == "ollama":
            try:
                r = requests.get(f"{self.host}/api/tags", timeout=5)
                return [m["name"] for m in r.json().get("models", [])]
            except Exception:
                return []
        return [self.model]

    # ── Génération ───────────────────────────────────────────────────

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        if self.provider == "ollama":
            return self._chat_ollama(messages, system_prompt, temperature, max_tokens)
        if self.provider == "anthropic":
            return self._chat_anthropic(messages, system_prompt, temperature, max_tokens)
        return self._chat_openai_compatible(messages, system_prompt, temperature, max_tokens)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        return self.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def embed(self, text: str) -> List[float]:
        # Cloud providers: utiliser sentence-transformers local
        if self.provider != "ollama":
            return self._embed_local(text)

        from config.settings import OLLAMA_EMBED_MODEL
        try:
            r = requests.post(
                f"{self.host}/api/embeddings",
                json={"model": OLLAMA_EMBED_MODEL, "prompt": text},
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("embedding", [])
        except Exception:
            return self._embed_local(text)

    # ── Provider implementations ─────────────────────────────────────

    def _chat_ollama(self, messages, system_prompt, temperature, max_tokens):
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system_prompt:
            payload["messages"] = [{"role": "system", "content": system_prompt}] + messages

        r = requests.post(f"{self.host}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()

    def _chat_openai_compatible(self, messages, system_prompt, temperature, max_tokens):
        base = self._base_urls.get(self.provider, "https://api.openai.com/v1")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        msgs = [{"role": "system", "content": system_prompt}] + messages if system_prompt else messages

        payload = {
            "model": self.model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _chat_anthropic(self, messages, system_prompt, temperature, max_tokens):
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()

    def _embed_local(self, text: str) -> List[float]:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode(text).tolist()
