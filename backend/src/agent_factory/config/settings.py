"""Application settings (environment + defaults)."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_models_yaml() -> Path:
    return Path(__file__).resolve().parent / "models.yaml"


# backend/ and repo-root .env (later files override earlier)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
_ENV_FILE_PATHS: tuple[str, ...] = tuple(
    str(p)
    for p in (_REPO_ROOT / ".env", _BACKEND_DIR / ".env")
    if p.is_file()
)


def _settings_config_dict() -> SettingsConfigDict:
    """Load dotenv from repo root then backend (backend wins on duplicate keys)."""
    base: dict[str, Any] = {
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
    if _ENV_FILE_PATHS:
        base["env_file"] = _ENV_FILE_PATHS
    return SettingsConfigDict(**base)


class Settings(BaseSettings):
    """Runtime configuration; secrets from env / K8s Secret."""

    model_config = _settings_config_dict()

    APP_ENV: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = Field(
        default=(
            "postgresql+asyncpg://agent:agent@localhost:55432/agent_factory"
        ),
    )
    DATABASE_POOL_SIZE: int = 20

    REDIS_URL: str = "redis://localhost:56379/0"
    REDIS_POOL_SIZE: int = 50

    MINIO_ENDPOINT: str = "localhost:59000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_BUCKET: str = "agent-factory"
    MINIO_USE_SSL: bool = False

    JWT_SECRET: str = Field(
        default="",
        description="HS256 secret for short-lived widget JWT",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_SECONDS: int = 300

    PORTAL_JWT_SECRET: str = Field(
        default="",
        description="HS256 secret to verify portal-issued JWT (exchange)",
    )
    PORTAL_JWT_PUBLIC_KEY: str = ""

    USER_ID_HASH_SALT: str = Field(
        default="dev-user-hash-salt-change-in-production",
        description="Pepper for user_id_hash (rotate via docs/21)",
    )

    SESSION_COOKIE_NAME: str = "session_id"
    SESSION_COOKIE_MAX_AGE: int = 1800
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "Strict"

    RATE_LIMIT_IP: int = 100
    RATE_LIMIT_USER: int = 60
    RATE_LIMIT_GLOBAL: int = 1000

    AUDIT_DEFAULT_LEVEL: str = "minimal"
    AUDIT_DEFAULT_RETAIN_DAYS: int = 90

    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    ADMIN_API_TOKEN: str = Field(
        default="",
        description="Bearer token for /api/v1/admin/* (empty = endpoints return 503)",
    )
    ADMIN_JWT_SECRET: str = Field(
        default="",
        description=(
            "HS256 secret for long-lived admin panel JWT; "
            "falls back to JWT_SECRET when empty."
        ),
    )
    ADMIN_PANEL_JWT_TTL_SECONDS: int = Field(
        default=604_800,
        ge=300,
        le=31_536_000,
        description="TTL for POST /auth/admin-login issued token.",
    )
    TOOL_DUAL_SIGN_ENABLED: bool = Field(
        default=False,
        description="When true, POST /tools creates pending_approval until approve.",
    )

    RBAC_LEGACY_AGENT_ADMIN_IMPLIES_FULL: bool = Field(
        default=True,
        description=(
            "If true, session permission agent.admin also implies skill.publish, "
            "tool.admin, audit.read, degradation.control, policy.admin (docs/51)."
        ),
    )
    RBAC_PERMISSION_CACHE_SECONDS: int = Field(
        default=300,
        ge=60,
        le=86400,
        description=(
            "Advisory TTL for permission snapshots (docs/12); exposed on GET /auth/me "
            "and used when rebuilding Redis session cache from DB."
        ),
    )

    MODELS_CONFIG_PATH: Path = Field(default_factory=_default_models_yaml)

    READY_CHECK_MINIO: bool = True
    READY_CHECK_MODEL_GATEWAY: bool = False

    INTERNAL_HTTP_TOOL_URL_PREFIXES: str = Field(
        default="",
        description=(
            "Comma-separated URL prefixes allowlist for Tool Registry "
            "implementation.type=http_api (see docs/09, docs/31). "
            "Empty disables registry HTTP tools."
        ),
    )
    INTERNAL_HTTP_TOOL_BEARER_TOKEN: str = Field(
        default="",
        description="Optional Bearer token for outbound internal HTTP tool calls.",
    )

    WORKSPACE_TOOLS_ENABLED: bool = Field(
        default=True,
        description=(
            "Enable fs.*/shell.exec/web.fetch built-in tools (OpenClaw-style workspace)."
        ),
    )
    WORKSPACE_ROOT: str = Field(
        default="",
        description=(
            "Sandbox root for fs.* and shell.exec; empty = repo root (parent of backend/)."
        ),
    )
    WORKSPACE_READ_MAX_CHARS: int = Field(default=120_000, ge=1000, le=2_000_000)
    WORKSPACE_GLOB_MAX_RESULTS: int = Field(default=500, ge=1, le=5000)
    WORKSPACE_GREP_MAX_RESULTS: int = Field(default=200, ge=1, le=2000)
    SHELL_EXEC_ENABLED: bool = Field(
        default=True,
        description="Allow shell.exec within WORKSPACE_ROOT (disable in production if needed).",
    )
    SHELL_EXEC_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=300)
    SHELL_EXEC_MAX_OUTPUT_CHARS: int = Field(default=32_000, ge=1000, le=500_000)
    WEB_FETCH_ENABLED: bool = Field(
        default=True,
        description="Allow web.fetch HTTP GET tool.",
    )
    WEB_FETCH_URL_PREFIXES: str = Field(
        default="http://,https://",
        description=(
            "Comma-separated URL prefixes allowlist for web.fetch; "
            "empty allows any http(s) URL."
        ),
    )
    WEB_FETCH_TIMEOUT_SECONDS: float = Field(default=20.0, ge=1.0, le=120.0)
    WEB_FETCH_MAX_CHARS: int = Field(default=80_000, ge=1000, le=500_000)

    WEB_SEARCH_ENABLED: bool = Field(
        default=True,
        description="Enable web.search (Baidu Qianfan AI Search).",
    )
    BAIDU_WEB_SEARCH_API_KEY: str = Field(
        default="",
        description="Baidu Qianfan / AppBuilder API Key (Bearer bce-v3/...).",
    )
    BAIDU_WEB_SEARCH_URL: str = Field(
        default="https://qianfan.baidubce.com/v2/ai_search/web_search",
        description="Baidu web_search endpoint.",
    )
    BAIDU_WEB_SEARCH_DEFAULT_TOP_K: int = Field(default=10, ge=1, le=50)
    BAIDU_WEB_SEARCH_MAX_TOP_K: int = Field(default=50, ge=1, le=50)
    BAIDU_WEB_SEARCH_EDITION: str = Field(
        default="standard",
        description="standard | lite",
    )
    BAIDU_WEB_SEARCH_TIMEOUT_SECONDS: float = Field(default=25.0, ge=3.0, le=120.0)

    MCP_CONTEXT7_ENABLED: bool = Field(default=True)
    MCP_CONTEXT7_COMMAND: str = Field(default="npx")
    MCP_CONTEXT7_ARGS: str = Field(
        default="-y,@upstash/context7-mcp@latest",
        description="Comma-separated args for Context7 MCP server.",
    )
    MCP_PLAYWRIGHT_ENABLED: bool = Field(default=True)
    MCP_PLAYWRIGHT_COMMAND: str = Field(default="npx")
    MCP_PLAYWRIGHT_ARGS: str = Field(
        default="-y,@playwright/mcp@latest",
        description="Comma-separated args for Playwright MCP server.",
    )
    MCP_CALL_TIMEOUT_SECONDS: float = Field(default=60.0, ge=5.0, le=300.0)

    MEMORY_TOOLS_ENABLED: bool = Field(default=True)
    MEMORY_GET_DEFAULT_LINES: int = Field(default=200, ge=10, le=2000)
    SESSIONS_TOOLS_ENABLED: bool = Field(default=True)
    SESSIONS_HISTORY_MAX_CHARS: int = Field(default=80_000, ge=1000, le=500_000)
    SESSIONS_SEND_MAX_TIMEOUT_SECONDS: float = Field(default=120.0, ge=0.0, le=600.0)
    SESSIONS_SPAWN_MAX_TIMEOUT_SECONDS: float = Field(default=300.0, ge=5.0, le=900.0)
    UI_TOOLS_ENABLED: bool = Field(default=True)
    AUTOMATION_TOOLS_ENABLED: bool = Field(default=True)
    MEDIA_TOOLS_ENABLED: bool = Field(default=True)
    MEDIA_VISION_MODEL: str = Field(default="", description="Override model for media.image")
    MEDIA_IMAGE_GENERATE_URL: str = Field(default="")
    MEDIA_IMAGE_GENERATE_API_KEY: str = Field(default="")
    MEDIA_IMAGE_GENERATE_MODEL: str = Field(default="")
    MEDIA_IMAGE_GENERATE_PROVIDER: str = Field(default="http")
    CODE_EXECUTION_ENABLED: bool = Field(default=True)
    CODE_EXECUTION_USE_GVISOR: bool = Field(default=False)
    CODE_EXECUTION_LLM_FALLBACK: bool = Field(default=True)
    CODE_EXECUTION_MODEL: str = Field(default="")
    CODE_EXECUTION_URL: str = Field(default="", description="Remote code_execution API (OpenClaw xAI parity)")
    CODE_EXECUTION_API_KEY: str = Field(default="")
    CODE_EXECUTION_TIMEOUT_SECONDS: int = Field(default=60, ge=5, le=300)
    CODE_EXECUTION_MAX_OUTPUT_CHARS: int = Field(default=32_000, ge=1000, le=500_000)

    WEB_X_SEARCH_ENABLED: bool = Field(default=True)
    X_SEARCH_API_URL: str = Field(default="")
    X_SEARCH_API_KEY: str = Field(default="")
    X_SEARCH_TIMEOUT_SECONDS: float = Field(default=30.0, ge=3.0, le=120.0)
    MESSAGING_TOOLS_ENABLED: bool = Field(default=True)
    NODES_TOOLS_ENABLED: bool = Field(default=True)
    MEDIA_MUSIC_GENERATE_URL: str = Field(default="")
    MEDIA_MUSIC_GENERATE_API_KEY: str = Field(default="")
    MEDIA_MUSIC_GENERATE_MODEL: str = Field(default="")
    MEDIA_VIDEO_GENERATE_URL: str = Field(default="")
    MEDIA_VIDEO_GENERATE_API_KEY: str = Field(default="")
    MEDIA_VIDEO_GENERATE_MODEL: str = Field(default="")

    MEDIA_PDF_MAX_PAGES: int = Field(default=20, ge=1, le=200)
    MEDIA_PDF_MAX_BYTES_MB: int = Field(default=10, ge=1, le=100)
    MEDIA_PDF_MAX_TEXT_CHARS: int = Field(default=80_000, ge=1000, le=500_000)
    MEDIA_PDF_LLM_INPUT_CHARS: int = Field(default=24_000, ge=1000, le=200_000)
    MEDIA_PDF_MODEL: str = Field(default="")

    MEDIA_TTS_URL: str = Field(default="")
    MEDIA_TTS_API_KEY: str = Field(default="")
    MEDIA_TTS_OPENAI_COMPAT: str = Field(
        default="",
        description="OpenAI-compatible TTS base URL (e.g. https://api.openai.com/v1)",
    )
    MEDIA_TTS_MODEL: str = Field(default="tts-1")
    MEDIA_TTS_VOICE: str = Field(default="alloy")
    MEDIA_TTS_TIMEOUT_SECONDS: float = Field(default=60.0, ge=5.0, le=300.0)
    MEDIA_TTS_MAX_CHARS: int = Field(default=4096, ge=100, le=32_000)

    KB_SEARCH_URL: str = Field(
        default="",
        description=(
            "POST URL for external kb.search (JSON: query, retrieval_scopes, "
            "optional scope). Empty = built-in stub only (prd §4, docs/09)."
        ),
    )
    KB_SEARCH_BEARER_TOKEN: str = Field(
        default="",
        description="Optional Bearer for KB_SEARCH_URL.",
    )
    KB_SEARCH_TIMEOUT_SECONDS: float = Field(
        default=12.0,
        ge=1.0,
        le=120.0,
        description="HTTP timeout for KB_SEARCH_URL.",
    )
    KB_SEARCH_ALLOW_HTTP: bool = Field(
        default=False,
        description=(
            "Allow http:// for KB_SEARCH_URL. Disable in production; "
            "see 信息安全 outbound URL policy."
        ),
    )
    KB_SEARCH_ALLOW_PRIVATE_HOSTS: bool = Field(
        default=False,
        description=(
            "Allow literal private/loopback IPs in KB_SEARCH_URL (isolated lab "
            "only; never on Internet-facing deployments)."
        ),
    )
    KB_SEARCH_REQUIRE_UPSTREAM: bool = Field(
        default=False,
        description=(
            "When true and KB_SEARCH_URL is set, kb.search fails if upstream "
            "is unavailable (no silent stub fallback)."
        ),
    )

    RISK_RULE_CHECK_URL: str = Field(
        default="",
        description="POST URL for partner risk.rule_check JSON API.",
    )
    RISK_RULE_CHECK_BEARER_TOKEN: str = Field(default="")
    RISK_RULE_CHECK_TIMEOUT_SECONDS: float = Field(default=15.0, ge=1.0, le=120.0)
    RISK_RULE_CHECK_ALLOW_HTTP: bool = Field(default=False)
    RISK_RULE_CHECK_ALLOW_PRIVATE_HOSTS: bool = Field(default=False)

    SKILL_GIT_IMPORT_ENABLED: bool = Field(
        default=True,
        description="Allow POST /skills/import-git (requires git on PATH).",
    )

    SCRIPT_HOOKS_ENABLED: bool = Field(
        default=False,
        description=(
            "P2: compile non-empty script_hooks and run preprocess/postprocess "
            "in Runner (docs/25). False preserves P0 empty hooks."
        ),
    )
    SCRIPT_WORKER_RUNTIME: str = Field(
        default="auto",
        description="subprocess | gvisor | auto (prefer gVisor when runsc exists).",
    )
    SCRIPT_GVISOR_RUNSC: str = Field(
        default="",
        description="Optional absolute path to runsc; empty uses PATH.",
    )
    SCRIPT_GVISOR_ROOTLESS: bool = Field(
        default=True,
        description="Pass --rootless to runsc do.",
    )
    WORKFLOW_DAG_ENABLED: bool = Field(
        default=True,
        description="P3: compile enterprise.workflow into RunSpec runtime.",
    )
    MULTI_SKILL_ENABLED: bool = Field(
        default=True,
        description=(
            "P3: merge agent skill_config.secondary_skills with tool/scope "
            "intersection."
        ),
    )
    ROUTER_AGENT_ENABLED: bool = Field(
        default=True,
        description="P3: enable POST /api/v1/agent-router/route.",
    )
    ROUTER_USE_LLM: bool = Field(
        default=True,
        description="Use model gateway for routing; fallback to keyword_v1.",
    )
    ROUTER_MODEL: str = Field(
        default="",
        description="Model id for router; empty uses DEGRADATION_CHAT_SMALL_MODEL.",
    )
    ROUTER_LLM_MAX_TOKENS: int = Field(default=256, ge=64, le=1024)

    AUTH_RATE_LIMIT_PER_MINUTE: int = Field(
        default=20,
        ge=5,
        le=300,
        description=(
            "Per-IP per-minute cap for /api/v1/auth/exchange|session|"
            "sync-permissions (brute-force / token stuffing mitigation)."
        ),
    )

    CHAT_USER_MESSAGE_MAX_CHARS: int = Field(
        default=32000,
        ge=1000,
        le=200000,
        description="Hard cap after Unicode sanitize on POST .../chat message.",
    )
    CHAT_RATE_LIMIT_PER_SESSION_PER_MINUTE: int = Field(
        default=45,
        ge=5,
        le=500,
        description="Per session_id per-minute cap on POST .../chat (abuse / 模型窃取).",
    )

    HSTS_MAX_AGE_SECONDS: int = Field(
        default=0,
        ge=0,
        le=63072000,
        description=(
            "If >0, send Strict-Transport-Security max-age (HTTPS deployments only)."
        ),
    )

    # ModelGateway reads these via ``models.yaml`` ``${NAME}`` (see docs/31).
    MINIMAX_API_KEY: str = ""
    QWEN3_32B_API_KEY: str = ""
    QWEN3_14B_API_KEY: str = ""
    QWEN3_8B_API_KEY: str = ""

    SKILL_EVAL_GATE_LIVE: bool = Field(
        default=False,
        description=(
            "If true, POST/PUT /skills runs live model scoring when "
            "package_metadata.eval_cases is non-empty (docs/27)."
        ),
    )
    SKILL_EVAL_GATE_MODEL: str = Field(
        default="",
        description=(
            "Override model for Registry eval gate; empty uses models.yaml "
            "defaults.model."
        ),
    )
    SKILL_EVAL_GATE_RPM: int = Field(
        default=0,
        ge=0,
        description=(
            "Max eval-gate model calls per minute (Redis fixed window). "
            "0 = use models.yaml RPM for the gate model (docs/10)."
        ),
    )
    SKILL_EVAL_CASES_REQUIRED: bool = Field(
        default=True,
        description=(
            "If true, POST/PUT /skills requires non-empty eval_cases or "
            "evals_inline in package_metadata (prd §8.5). "
            "Set false for legacy imports."
        ),
    )

    SESSION_CHAT_LOCK_MAX_WAITERS: int = Field(
        default=8,
        ge=0,
        description=(
            "Max concurrent waiters per session for POST .../chat lock "
            "(0 = fail immediately with SESSION_BUSY). docs/plan §12."
        ),
    )
    SESSION_CHAT_LOCK_WAIT_MS: int = Field(
        default=45000,
        ge=1000,
        description="Upper bound for waiting on session chat lock (milliseconds).",
    )
    SESSION_CHAT_LOCK_POLL_MS: int = Field(
        default=150,
        ge=50,
        description="Poll interval while waiting for session chat lock (milliseconds).",
    )

    MODEL_QUEUE_ENABLED: bool = Field(
        default=True,
        description="ZSET priority queue + inflight cap before model HTTP (docs/10).",
    )
    MODEL_QUEUE_CAP_PRIVILEGED: int = Field(default=32, ge=0)
    MODEL_QUEUE_CAP_INTERACTIVE: int = Field(default=64, ge=0)
    MODEL_QUEUE_CAP_DOCUMENT: int = Field(default=24, ge=0)
    MODEL_QUEUE_CAP_BATCH: int = Field(default=16, ge=0)
    MODEL_QUEUE_CAP_EMBEDDING: int = Field(
        default=32,
        ge=0,
        description="Reserved pool for future Embedding/Rerank (docs/10).",
    )
    MODEL_QUEUE_CAP_RERANK: int = Field(
        default=24,
        ge=0,
        description="Separate inflight cap for rerank-heavy embedding path.",
    )
    MODEL_QUEUE_ACQUIRE_TIMEOUT_MS: int = Field(
        default=120_000,
        ge=500,
        description="Max wait to acquire a model queue slot (ms).",
    )
    MODEL_QUEUE_POLL_MS: int = Field(
        default=50,
        ge=10,
        description="Poll interval while waiting for a model queue slot (ms).",
    )
    MODEL_QUEUE_MAX_ZQUEUE_PRIVILEGED: int = Field(
        default=100,
        ge=1,
        description="Max waiting tickets per class ZSET (docs/10).",
    )
    MODEL_QUEUE_MAX_ZQUEUE_INTERACTIVE: int = Field(default=1000, ge=1)
    MODEL_QUEUE_MAX_ZQUEUE_DOCUMENT: int = Field(default=500, ge=1)
    MODEL_QUEUE_MAX_ZQUEUE_BATCH: int = Field(default=2000, ge=1)
    MODEL_QUEUE_SOFT_ZCARD_INTERACTIVE: int = Field(
        default=900,
        ge=1,
        description="ZCARD soft limit → preflight 429 (docs/10).",
    )
    MODEL_QUEUE_SOFT_ZCARD_DOCUMENT: int = Field(default=450, ge=1)
    MODEL_QUEUE_SOFT_ZCARD_PRIVILEGED: int = Field(default=98, ge=1)
    MODEL_QUEUE_RETRY_AFTER_INTERACTIVE: int = Field(default=5, ge=1)
    MODEL_QUEUE_RETRY_AFTER_DOCUMENT: int = Field(default=30, ge=1)
    MODEL_QUEUE_RETRY_AFTER_PRIVILEGED: int = Field(default=10, ge=1)
    MODEL_QUEUE_AGING_SEC_1: float = Field(default=30.0, ge=1.0)
    MODEL_QUEUE_AGING_SEC_2: float = Field(default=60.0, ge=1.0)
    MODEL_QUEUE_AGING_SEC_3: float = Field(default=120.0, ge=1.0)
    MODEL_QUEUE_AGING_DELTA_1: float = Field(
        default=1e14,
        ge=1.0,
        description="ZINCRBY delta (negative priority boost) after sec1.",
    )
    MODEL_QUEUE_AGING_DELTA_2: float = Field(default=1e14, ge=1.0)
    MODEL_QUEUE_AGING_FORCE_DELTA: float = Field(
        default=5e15,
        ge=1.0,
        description="Strong boost after sec3 (near force dequeue).",
    )

    EMBEDDING_ENDPOINT: str = Field(
        default="",
        description=(
            "OpenAI-compatible embeddings base URL (e.g. "
            "https://api.openai.com/v1); empty uses local hash stub."
        ),
    )
    EMBEDDING_API_KEY: str = Field(default="", description="Bearer for embeddings.")
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-3-small",
        description="Embeddings model id for batch API.",
    )
    EMBEDDING_BATCH_WINDOW_MS: int = Field(
        default=100,
        ge=10,
        le=5000,
        description="Coalesce embedding requests (docs/10 §Embedding).",
    )
    EMBEDDING_BATCH_MAX_ITEMS: int = Field(
        default=64,
        ge=1,
        le=2048,
        description="Max texts per batch flush.",
    )
    EMBEDDING_HTTP_TIMEOUT_SECONDS: float = Field(
        default=60.0,
        ge=5.0,
        description="HTTP timeout for one embedding batch call.",
    )

    DEGRADATION_AUTO_ENABLED: bool = Field(
        default=False,
        description=(
            "Cron: auto escalate / step-down degradation from model signals "
            "(docs/13). Enable after threshold tuning."
        ),
    )
    DEGRADATION_AUTO_WINDOW_MINUTES: int = Field(default=3, ge=1, le=60)
    DEGRADATION_AUTO_ESCALATE_ERROR_RATE: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Align prd §9.5: error rate > 5% triggers escalation.",
    )
    DEGRADATION_AUTO_RECOVER_MAX_ERROR_RATE: float = Field(
        default=0.01,
        ge=0.0,
        le=1.0,
        description="prd §9.5: full recover when failure rate < 1%.",
    )
    DEGRADATION_AUTO_GOOD_STREAK_SECONDS: int = Field(
        default=300,
        ge=30,
        description="Good metrics sustained before one auto step-down.",
    )
    DEGRADATION_AUTO_LATENCY_ESCALATE_MS: float = Field(
        default=30_000.0,
        ge=1000.0,
        description="Align prd §9.5: queue P99 ~30s tier; EMA above this escalates.",
    )
    DEGRADATION_AUTO_LATENCY_RECOVER_MS: float = Field(
        default=8000.0,
        ge=100.0,
        description="Latency EMA below this allows recovery path.",
    )
    DEGRADATION_AUTO_MIN_ATTEMPTS_FOR_RECOVER: int = Field(
        default=8,
        ge=0,
        description="Min attempts in window before auto step-down.",
    )

    DEGRADATION_LATENCY_REDUCE_TOPK_MS: float = Field(
        default=60_000.0,
        ge=1000.0,
        description="prd §9.5: above this EMA, kb top_k reduced.",
    )
    DEGRADATION_LATENCY_SMALL_MODEL_MS: float = Field(
        default=120_000.0,
        ge=1000.0,
        description="prd §9.5: above this EMA, optional small chat model.",
    )
    DEGRADATION_KB_TOP_K_REDUCED: int = Field(
        default=5,
        ge=1,
        le=100,
        description="prd §9.5: reduced retrieval top_k (from 20).",
    )
    DEGRADATION_MAX_TURNS_ON_ERROR_ESCALATION: int = Field(
        default=3,
        ge=1,
        le=50,
        description="prd §9.5: cap max_turns when error rate >= escalate.",
    )
    DEGRADATION_CHAT_SMALL_MODEL: str = Field(
        default="",
        description=(
            "Logical model id (models.yaml) when latency EMA exceeds "
            "DEGRADATION_LATENCY_SMALL_MODEL_MS; empty skips."
        ),
    )

    TOOL_HTTP_CIRCUIT_ENABLED: bool = Field(
        default=True,
        description="Redis circuit breaker for Registry http_api tools (docs/09).",
    )
    TOOL_HTTP_CIRCUIT_FAILURE_THRESHOLD: int = Field(
        default=5,
        ge=1,
        description="Failures in window before opening circuit.",
    )
    TOOL_HTTP_CIRCUIT_WINDOW_SECONDS: int = Field(
        default=60,
        ge=1,
        description="Rolling window for failure counting.",
    )
    TOOL_HTTP_CIRCUIT_OPEN_SECONDS: int = Field(
        default=30,
        ge=1,
        description="TTL for open circuit (reject fast).",
    )
    TOOL_HTTP_CIRCUIT_PER_DEPARTMENT: bool = Field(
        default=True,
        description=(
            "If true, circuit scope includes session department "
            "(when set)."
        ),
    )

    DOC_PARSE_ASYNC_MIN_BYTES: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        description=(
            "Enqueue Redis doc_jobs after upload when size >= this "
            "(docs/24)."
        ),
    )
    DOC_PARSE_QUEUE_FORCE_ASYNC_DEPTH: int = Field(
        default=100,
        ge=1,
        description=(
            "When Redis doc_jobs stream length >= this, enqueue parse for "
            "any upload size (prd §9.5)."
        ),
    )

    MAU_RETENTION_GATE_ENABLED: bool = Field(
        default=False,
        description=(
            "Cron: mark agents cold when 30d MAU below threshold; "
            "archive long-idle cold (docs/21, prd §15.1). "
            "Default off so dev seeds are not flipped cold without tuning."
        ),
    )
    MAU_RETENTION_WINDOW_DAYS: int = Field(default=30, ge=1, le=365)
    MAU_RETENTION_DEFAULT_THRESHOLD: int = Field(
        default=5,
        ge=0,
        description="Distinct user_id_hash in window below → cold.",
    )
    MAU_COLD_ARCHIVE_AFTER_DAYS: int = Field(
        default=90,
        ge=1,
        description="Days in cold before auto-archived.",
    )

    OTEL_ENABLED: bool = Field(
        default=False,
        description="Export traces via OTLP/HTTP (optional observability extra).",
    )
    OTEL_SERVICE_NAME: str = Field(
        default="agent-factory-api",
        description="OpenTelemetry service.name resource attribute.",
    )
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: str = Field(
        default="",
        description=(
            "OTLP/HTTP endpoint for traces, e.g. "
            "http://otel-collector:4318/v1/traces"
        ),
    )
    OTEL_TRACES_SAMPLER_RATIO: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="TraceIdRatioBased sampler for root spans.",
    )

    FEISHU_ENABLED: bool = Field(
        default=False,
        description="Enable Feishu/Lark bot channel (WebSocket or webhook).",
    )
    FEISHU_APP_ID: str = Field(default="", description="Feishu app_id (cli_xxx).")
    FEISHU_APP_SECRET: str = Field(default="", description="Feishu app secret.")
    FEISHU_VERIFICATION_TOKEN: str = Field(
        default="",
        description="Event subscription verification token (webhook mode).",
    )
    FEISHU_ENCRYPT_KEY: str = Field(
        default="",
        description="Event subscription encrypt key (optional).",
    )
    FEISHU_CONNECTION_MODE: str = Field(
        default="ws",
        description="ws / websocket (long connection) or webhook.",
    )
    FEISHU_DOMAIN: str = Field(
        default="feishu",
        description="feishu (CN) or lark (international) API domain.",
    )
    FEISHU_DEFAULT_AGENT_ID: str = Field(
        default="",
        description="Fallback agent when router cannot decide.",
    )
    FEISHU_CANDIDATE_AGENT_IDS: str = Field(
        default="",
        description="Comma-separated agent ids for intent routing; empty = all active.",
    )
    FEISHU_GROUP_REQUIRE_MENTION: bool = Field(
        default=True,
        description="In group chats, only respond when bot is @mentioned.",
    )
    FEISHU_DM_POLICY: str = Field(
        default="open",
        description="DM policy: open | disabled.",
    )
    FEISHU_DEPARTMENT: str = Field(
        default="feishu",
        description="department field on Feishu-origin sessions.",
    )
    FEISHU_ROUTE_EACH_TURN: bool = Field(
        default=False,
        description="Re-run agent router on every user message (else sticky per chat).",
    )
    FEISHU_ROUTER_USE_LLM: bool = Field(
        default=True,
        description="Use LLM router for Feishu; fallback keyword heuristic.",
    )
    FEISHU_REPLY_MAX_CHARS: int = Field(
        default=3800,
        ge=500,
        le=20000,
        description="Split outbound Feishu text replies above this size.",
    )
    FEISHU_REPLY_USE_MARKDOWN: bool = Field(
        default=True,
        description="Send assistant replies as interactive markdown cards.",
    )
    FEISHU_CHANNEL_EXTRA_TOOLS: str = Field(
        default="feishu.doc,agent.list",
        description="Extra tools injected for Feishu channel sessions (comma-separated).",
    )
    FEISHU_MAX_TURNS: int = Field(
        default=0,
        ge=0,
        le=128,
        description=(
            "Max model/tool rounds per single Feishu message. "
            "0 = generous cap (64), same chat thread has no message-count limit."
        ),
    )
    FEISHU_SESSION_TTL_DAYS: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Feishu chat binding TTL in Redis (same thread reuses session).",
    )

    @property
    def feishu_channel_extra_tools(self) -> list[str]:
        return [
            x.strip()
            for x in self.FEISHU_CHANNEL_EXTRA_TOOLS.split(",")
            if x.strip()
        ]

    DEV_WIDGET_AUTH_BYPASS: bool = Field(
        default=False,
        description=(
            "Only when APP_ENV=development: POST /auth/dev/session creates a "
            "session without portal JWT (local Widget UX)."
        ),
    )

    MODEL_DEV_MOCK: bool = Field(
        default=False,
        description=(
            "Only when APP_ENV=development: ModelGateway streams a stub reply "
            "without calling external chat APIs (avoids 502 when no vendor URL)."
        ),
    )

    @field_validator("MODELS_CONFIG_PATH", mode="before")
    @classmethod
    def _coerce_models_path(cls, v: object) -> Path:
        if isinstance(v, Path):
            return v
        if isinstance(v, str):
            return Path(v)
        return _default_models_yaml()

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def internal_http_tool_url_prefixes(self) -> list[str]:
        """Non-empty prefixes required for registry-backed http_api tools."""
        return [
            p.strip()
            for p in self.INTERNAL_HTTP_TOOL_URL_PREFIXES.split(",")
            if p.strip()
        ]

    @property
    def web_fetch_url_prefixes(self) -> list[str]:
        return [
            p.strip()
            for p in self.WEB_FETCH_URL_PREFIXES.split(",")
            if p.strip()
        ]

    @property
    def feishu_api_base(self) -> str:
        domain = self.FEISHU_DOMAIN.strip().lower()
        if domain == "lark":
            return "https://open.larksuite.com"
        if domain.startswith("http://") or domain.startswith("https://"):
            return domain.rstrip("/")
        return "https://open.feishu.cn"

    @property
    def feishu_candidate_agent_ids(self) -> list[str]:
        return [
            x.strip()
            for x in self.FEISHU_CANDIDATE_AGENT_IDS.split(",")
            if x.strip()
        ]

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic (psycopg3)."""
        u = self.DATABASE_URL
        if "+asyncpg" in u:
            return u.replace("postgresql+asyncpg", "postgresql+psycopg", 1)
        return u


@lru_cache
def get_settings() -> Settings:
    return Settings()
