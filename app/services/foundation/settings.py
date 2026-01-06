#!/usr/bin/env python3
"""Centralized application settings loaded from environment variables."""

import os
from functools import lru_cache
from typing import Optional

# Best-effort: load .env even in fallback or mixed environments
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(override=True)
except Exception:
    pass


def _env_first(names: list[str], default: Optional[str] = None) -> Optional[str]:
    for name in names:
        if not name:
            continue
        value = os.getenv(name)
        if value:
            return value
    return default


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


class AppSettings:
    """Lightweight settings loaded from environment variables."""

    def __init__(self) -> None:
        # Logging
        self.log_level: str = _env_str("LOG_LEVEL", "INFO")
        self.log_format: str = _env_str("LOG_FORMAT", "json")

        # Database
        self.database_url: str = _env_str("DATABASE_URL", "sqlite:///./tasks.db")
        self.base_url: Optional[str] = os.getenv("BASE_URL")

        # GLM / LLM
        self.glm_api_key: Optional[str] = os.getenv("GLM_API_KEY")
        self.glm_api_url: str = _env_str(
            "GLM_API_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        )
        self.glm_model: str = _env_str("GLM_MODEL", "glm-4-flash")
        self.glm_request_timeout: int = _env_int("GLM_REQUEST_TIMEOUT", 60)
        self.llm_request_timeout: int = _env_int("LLM_REQUEST_TIMEOUT", 60)
        self.llm_mock: bool = _env_bool("LLM_MOCK", False)
        self.llm_retries: int = _env_int("LLM_RETRIES", 2)
        self.llm_backoff_base: float = _env_float("LLM_BACKOFF_BASE", 0.5)

        # Perplexity
        self.perplexity_api_key: Optional[str] = os.getenv("PERPLEXITY_API_KEY")
        self.perplexity_api_url: str = _env_str(
            "PERPLEXITY_API_URL", "https://api.perplexity.ai/chat/completions"
        )
        self.perplexity_model: str = _env_str("PERPLEXITY_MODEL", "sonar-reasoning-pro")

        # Doubao
        self.doubao_api_key: Optional[str] = os.getenv("DOUBAO_API_KEY")
        self.doubao_api_url: str = _env_str(
            "DOUBAO_API_URL", "https://ark.cn-beijing.volces.com/api/v3"
        )
        self.doubao_model: str = _env_str("DOUBAO_MODEL", "doubao-seed-1-6-251015")

        # Moonshot / Kimi
        self.moonshot_api_key: Optional[str] = os.getenv("MOONSHOT_API_KEY")
        self.moonshot_api_url: str = _env_str("MOONSHOT_API_URL", "https://api.moonshot.cn/v1")
        self.moonshot_model: str = _env_str("MOONSHOT_MODEL", "kimi-k2-turbo-preview")

        # DeepSeek
        self.deepseek_api_key: Optional[str] = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_api_url: str = _env_str("DEEPSEEK_API_URL", "https://api.deepseek.com")
        self.deepseek_model: str = _env_str("DEEPSEEK_MODEL", "deepseek-chat")

        # Grok / xAI
        self.grok_api_key: Optional[str] = os.getenv("GROK_API_KEY")
        self.grok_api_url: str = _env_str("GROK_API_URL", "https://api.x.ai/v1")
        self.grok_model: str = _env_str("GROK_MODEL", "grok-4")

        # Gemini
        self.gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
        self.gemini_api_url: str = _env_str(
            "GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self.gemini_model: str = _env_str("GEMINI_MODEL", "gemini-2.5-flash")

        # QWEN
        self.qwen_api_key: Optional[str] = os.getenv("QWEN_API_KEY")
        self.qwen_api_url: str = _env_str(
            "QWEN_API_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        )
        self.qwen_model: str = _env_str("QWEN_MODEL", "qwen-turbo")

        # Provider selection
        self.llm_provider: str = _env_str("LLM_PROVIDER", "glm")

        # Embeddings
        self.glm_embeddings_api_url: Optional[str] = os.getenv("GLM_EMBEDDINGS_API_URL")
        self.glm_embedding_model: str = _env_str("GLM_EMBEDDING_MODEL", "embedding-3")
        self.glm_embedding_dimension: int = _env_int("GLM_EMBEDDING_DIM", 1536)
        self.glm_batch_size: int = _env_int("GLM_BATCH_SIZE", 25)
        self.semantic_default_k: int = _env_int("SEMANTIC_DEFAULT_K", 5)
        self.semantic_min_similarity: float = _env_float("SEMANTIC_MIN_SIMILARITY", 0.3)
        self.glm_max_retries: int = _env_int("GLM_MAX_RETRIES", 3)
        self.glm_retry_delay: float = _env_float("GLM_RETRY_DELAY", 1.0)
        self.glm_debug: bool = _env_bool("GLM_DEBUG", False)

        # Embedding cache
        self.embedding_cache_size: int = _env_int("EMBEDDING_CACHE_SIZE", 10000)
        self.embedding_cache_persistent: bool = _env_bool("EMBEDDING_CACHE_PERSISTENT", True)

        # Context/debug flags
        self.ctx_debug: bool = _env_bool("CTX_DEBUG", False) or _env_bool("CONTEXT_DEBUG", False)
        self.budget_debug: bool = _env_bool("BUDGET_DEBUG", False)
        self.decomp_debug: bool = _env_bool("DECOMP_DEBUG", False)
        self.global_index_path: str = _env_str("GLOBAL_INDEX_PATH", "INDEX.md")

        # External providers
        self.openai_api_key: Optional[str] = _env_first(["OPENAI_API_KEY", "GPT_API_KEY"])
        self.xai_api_key: Optional[str] = _env_first(["XAI_API_KEY", "GROK_API_KEY"])
        self.anthropic_api_key: Optional[str] = _env_first(["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"])
        self.tavily_api_key: Optional[str] = os.getenv("TAVILY_API_KEY")

        # Server
        self.backend_host: str = _env_str("BACKEND_HOST", "0.0.0.0")
        self.backend_port: int = _env_int("BACKEND_PORT", 9000)
        self.cors_origins: str = _env_str(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
        )
        self.chat_include_action_summary: bool = _env_bool("CHAT_INCLUDE_ACTION_SUMMARY", True)
        self.job_log_retention_days: int = _env_int("JOB_LOG_RETENTION_DAYS", 30)
        self.job_log_max_rows: int = _env_int("JOB_LOG_MAX_ROWS", 10000)

        # Simulation
        self.sim_user_model: str = _env_str("SIM_USER_MODEL", "qwen3-max")
        self.sim_judge_model: str = _env_str("SIM_JUDGE_MODEL", "qwen3-max")
        self.sim_default_turns: int = _env_int("SIM_DEFAULT_TURNS", 5)
        self.sim_max_turns: int = _env_int("SIM_MAX_TURNS", 10)
        self.sim_default_goal: str = _env_str(
            "SIM_DEFAULT_GOAL",
            "Refine the currently bound plan to better achieve the user's objectives.",
        )

        # Memory
        self.memory_auto_save_enabled: bool = _env_bool("MEMORY_AUTO_SAVE_ENABLED", True)
        self.memory_retrieve_enabled: bool = _env_bool("MEMORY_RETRIEVE_ENABLED", True)
        self.memory_query_limit: int = _env_int("MEMORY_QUERY_LIMIT", 5)
        self.memory_min_similarity: float = _env_float("MEMORY_MIN_SIMILARITY", 0.6)
        self.memory_text_similarity: float = _env_float("MEMORY_TEXT_SIMILARITY", 1.0)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings."""
    settings = AppSettings()

    # Ensure BASE_URL fallback stays in sync with BACKEND_HOST/BACKEND_PORT
    if not settings.base_url:
        settings.base_url = f"http://{settings.backend_host}:{settings.backend_port}"

    return settings
