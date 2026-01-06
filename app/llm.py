import json
import os
import random
import time
from typing import Any, Dict, Optional, Sequence
from urllib import error, request

from .interfaces import LLMProvider
from .services.foundation.settings import get_settings

PROVIDER_CONFIGS: Dict[str, Dict[str, Any]] = {
    "glm": {
        "api_key_env": "GLM_API_KEY",
        "url_env": "GLM_API_URL",
        "model_env": "GLM_MODEL",
        "settings_api_key": "glm_api_key",
        "settings_url": "glm_api_url",
        "settings_model": "glm_model",
        "default_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "default_model": "glm-4-flash",
        "endpoint_path": "",
    },
    "perplexity": {
        "api_key_env": "PERPLEXITY_API_KEY",
        "url_env": "PERPLEXITY_API_URL",
        "model_env": "PERPLEXITY_MODEL",
        "settings_api_key": "perplexity_api_key",
        "settings_url": "perplexity_api_url",
        "settings_model": "perplexity_model",
        "default_url": "https://api.perplexity.ai/chat/completions",
        "default_model": "sonar-reasoning-pro",
        "endpoint_path": "",
    },
    "qwen": {
        "api_key_env": "QWEN_API_KEY",
        "url_env": "QWEN_API_URL",
        "model_env": "QWEN_MODEL",
        "settings_api_key": "qwen_api_key",
        "settings_url": "qwen_api_url",
        "settings_model": "qwen_model",
        "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "default_model": "qwen-turbo",
        "endpoint_path": "",
    },
    "doubao": {
        "api_key_env": ["DOUBAO_API_KEY", "ARK_API_KEY"],
        "url_env": "DOUBAO_API_URL",
        "model_env": "DOUBAO_MODEL",
        "settings_api_key": "doubao_api_key",
        "settings_url": "doubao_api_url",
        "settings_model": "doubao_model",
        "default_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-seed-1-6-251015",
        "endpoint_path": "/chat/completions",
    },
    "moonshot": {
        "api_key_env": "MOONSHOT_API_KEY",
        "url_env": "MOONSHOT_API_URL",
        "model_env": "MOONSHOT_MODEL",
        "settings_api_key": "moonshot_api_key",
        "settings_url": "moonshot_api_url",
        "settings_model": "moonshot_model",
        "default_url": "https://api.moonshot.cn/v1",
        "default_model": "kimi-k2-turbo-preview",
        "endpoint_path": "/chat/completions",
    },
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "url_env": "DEEPSEEK_API_URL",
        "model_env": "DEEPSEEK_MODEL",
        "settings_api_key": "deepseek_api_key",
        "settings_url": "deepseek_api_url",
        "settings_model": "deepseek_model",
        "default_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "endpoint_path": "/chat/completions",
    },
    "grok": {
        "api_key_env": ["GROK_API_KEY", "XAI_API_KEY"],
        "url_env": ["GROK_API_URL", "XAI_API_URL"],
        "model_env": ["GROK_MODEL", "XAI_MODEL"],
        "settings_api_key": "grok_api_key",
        "settings_url": "grok_api_url",
        "settings_model": "grok_model",
        "default_url": "https://api.x.ai/v1",
        "default_model": "grok-4",
        "endpoint_path": "/chat/completions",
    },
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "url_env": "GEMINI_API_URL",
        "model_env": "GEMINI_MODEL",
        "settings_api_key": "gemini_api_key",
        "settings_url": "gemini_api_url",
        "settings_model": "gemini_model",
        "default_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.5-flash",
        "endpoint_path": "/chat/completions",
    },
}

DEFAULT_PROVIDER = "glm"


def _first_env_value(names: Optional[Sequence[str] | str]) -> Optional[str]:
    if not names:
        return None
    if isinstance(names, str):
        names = [names]
    for name in names:
        if not name:
            continue
        value = os.getenv(name)
        if value:
            return value
    return None


def _get_settings_attr(settings: Any, attr: Optional[str]) -> Optional[str]:
    if not attr:
        return None
    return getattr(settings, attr, None)


def _compose_endpoint(base_url: str, path: Optional[str]) -> str:
    if not path:
        return base_url
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _truthy(val: Optional[str]) -> bool:
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}


class LLMClient(LLMProvider):
    """
    Multi-provider LLM client supporting GLM, Perplexity, and other APIs.

    Responsibilities:
    - Manage API configuration for different providers
    - Provide chat() to get completion content
    - Provide ping() for connectivity check
    - Auto-switch providers based on configuration
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 60,
        retries: Optional[int] = None,
        backoff_base: Optional[float] = None,
    ) -> None:
        settings = get_settings()
        provider_name = provider or os.getenv("LLM_PROVIDER") or getattr(settings, "llm_provider", DEFAULT_PROVIDER)
        provider_name = (provider_name or DEFAULT_PROVIDER).lower()
        config = PROVIDER_CONFIGS.get(provider_name)
        if not config:
            raise ValueError(f"Unsupported LLM provider: {provider_name}")

        env_api_key = _first_env_value(config.get("api_key_env"))
        env_url = _first_env_value(config.get("url_env"))
        env_model = _first_env_value(config.get("model_env"))

        settings_api_key = _get_settings_attr(settings, config.get("settings_api_key"))
        settings_url = _get_settings_attr(settings, config.get("settings_url"))
        settings_model = _get_settings_attr(settings, config.get("settings_model"))

        self.provider = provider_name
        self.api_key = api_key or env_api_key or settings_api_key
        self.url = str(url or env_url or settings_url or config.get("default_url") or "")
        self.model = model or env_model or settings_model or config.get("default_model")
        self.extra_headers: Dict[str, str] = config.get("headers", {})
        self.payload_defaults: Dict[str, Any] = config.get("payload_defaults", {})
        if not self.url:
            raise RuntimeError(f"{self.provider.upper()} base URL is not configured.")
        self.endpoint_url = _compose_endpoint(self.url, config.get("endpoint_path"))

        if not self.api_key:
            raise RuntimeError(
                f"{self.provider.upper()}_API_KEY is not configured. "
                f"Set environment variable {config.get('api_key_env')} or update settings."
            )

        self.timeout = timeout or getattr(settings, "llm_request_timeout", 60)
        # 🚫 科研项目要求：强制禁用Mock模式，必须使用真实API
        self.mock = False  # 永远不使用Mock模式
        # Retry/backoff configuration
        try:
            if retries is None:
                env_r = os.getenv("LLM_RETRIES")
                self.retries = int(env_r) if env_r is not None else int(settings.llm_retries)
            else:
                self.retries = int(retries)
        except Exception:
            self.retries = 2
        try:
            if backoff_base is None:
                env_b = os.getenv("LLM_BACKOFF_BASE")
                self.backoff_base = float(env_b) if env_b is not None else float(settings.llm_backoff_base)
            else:
                self.backoff_base = float(backoff_base)
        except Exception:
            self.backoff_base = 0.5

    def chat(self, prompt: str, force_real: bool = False, model: Optional[str] = None, **_: Any) -> str:
        if self.mock and not force_real:
            return "This is a mock completion."

        if not self.api_key:
            raise RuntimeError(f"{self.provider.upper()}_API_KEY is not set in environment")
        # Use structured content blocks to satisfy providers that require `type: text`.
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ]
        payload = {
            "model": model or self.model,
            "messages": messages,
        }
        if self.payload_defaults:
            payload.update(self.payload_defaults)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        headers.update(self.extra_headers)
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(self.endpoint_url, data=data, headers=headers, method="POST")

        for attempt in range(self.retries + 1):
            try:
                with request.urlopen(req, timeout=self.timeout) as resp:
                    resp_text = resp.read().decode("utf-8")
                    obj = json.loads(resp_text)
                try:
                    return obj["choices"][0]["message"]["content"]
                except Exception:
                    raise RuntimeError(f"Unexpected LLM response: {obj}")
            except error.HTTPError as e:
                # Retry only for 5xx; surface 4xx immediately
                code = getattr(e, "code", None)
                if isinstance(code, int) and 500 <= code < 600 and attempt < self.retries:
                    # backoff retry
                    delay = max(0.0, self.backoff_base * (2**attempt) + random.uniform(0, self.backoff_base / 4.0))
                    time.sleep(delay)
                    continue
                try:
                    msg = e.read().decode("utf-8")
                except Exception:
                    msg = str(e)
                raise RuntimeError(f"LLM HTTPError: {e.code} {msg}")
            except Exception as e:
                # Treat as transient (network) and retry
                if attempt < self.retries:
                    delay = max(0.0, self.backoff_base * (2**attempt) + random.uniform(0, self.backoff_base / 4.0))
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"LLM request failed: {e}")
        raise RuntimeError("LLM request failed after retries")

    def ping(self) -> bool:
        if self.mock:
            return True
        try:
            _ = self.chat("ping")
            return True
        except Exception:
            return False

    def config(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "model": self.model,
            "has_api_key": bool(self.api_key),
            "mock": bool(self.mock),
        }


_default_client: Optional[LLMClient] = None


def get_default_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
