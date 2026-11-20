"""全局配置：从环境变量 / .env 读取（pydantic-settings）。

设计原则：LLM、Embedding、VL 均为可插拔 provider，
切换云端/本地只改环境变量，业务代码不变。
"""
from __future__ import annotations

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- 对话大模型 ----
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ---- Embedding ----
    embedding_provider: str = "local"  # local | dashscope
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512
    dashscope_api_key: str = ""
    dashscope_embedding_model: str = "text-embedding-v3"
    # DashScope OpenAI 兼容端点（国内站 / 国际站二选一，按账号开通地区）
    # 国内站: https://dashscope.aliyuncs.com/compatible-mode/v1
    # 国际站: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ---- 多模态（M2）----
    vl_provider: str = "dashscope"
    dashscope_vl_model: str = "qwen-vl-max"

    # ---- 数据库 ----
    database_url: str = "sqlite:///./app.db"

    # ---- 运行环境 / 安全 ----
    environment: str = "development"  # development | production
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    max_pdf_upload_mb: int = 50
    max_image_upload_mb: int = 10

    # ---- 鉴权 ----
    # 注意：默认空字符串，必须通过环境变量或 .env 配置安全值
    jwt_secret: str = ""
    jwt_expire_minutes: int = 720
    jwt_algorithm: str = "HS256"

    # ---- 检索 ----
    retrieve_top_k: int = 4
    vector_backend: str = "auto"        # auto | python | pgvector
    retrieval_mode: str = "hybrid"      # hybrid | vector | lexical
    hybrid_rrf_k: int = 60
    hybrid_candidate_k: int = 50
    query_rewrite_enabled: bool = True   # 进阶：检索前把口语 query 改写为工业术语
    graph_rag_enabled: bool = True       # 进阶：Graph RAG，注入知识图谱邻居作结构化上下文
    parent_child_enabled: bool = True    # 进阶：父子分块，召回子块、喂模型父块上下文
    parent_window: int = 1               # 父块向同文档相邻各扩展的块数

    # ---- Agent 诊断 ----
    agent_max_iterations: int = 8
    agent_min_distinct_tools: int = 2
    agent_parse_retries: int = 1
    agent_tool_budget_seconds: float = 15.0

    # ---- 接口限流（进阶，保护云端 API 额度）----
    rate_limit_enabled: bool = True
    rate_limit_chat: int = 20            # 每用户每分钟问答次数（审核员/管理员 ×3）
    rate_limit_upload: int = 10          # 每用户每分钟图片/上传次数（审核员/管理员 ×3）

    # ---- 离线/局域网模式（进阶预案）----
    # 标识离线部署；LLM/VL 实际切换由 deepseek_base_url / dashscope_base_url 指向
    # 局域网 Ollama/vLLM（OpenAI 兼容），Embedding 切本地 fastembed，均只改 .env
    offline_mode: bool = False

    # ---- 故障图片双重校验（安全拦截）----
    # VL 判定为非工业故障 / 置信度低于阈值时，拦截不走后续检索，避免"一本正经胡编"
    image_confidence_threshold: float = 0.6


settings = Settings()


def cors_origin_list() -> list[str]:
    """解析允许跨域访问的来源；生产环境不允许使用通配符。"""
    origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
    return origins or ["http://127.0.0.1:5173", "http://localhost:5173"]


def validate_runtime_settings() -> None:
    """启动时校验关键安全配置，避免演示配置误带到生产环境。"""
    # 所有环境都要求配置 JWT_SECRET
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        raise RuntimeError(
            "JWT_SECRET 必须配置且长度至少 32 字符，请在 .env 中设置强随机字符串"
        )
    # 开发环境的弱密钥给警告但不阻断
    if settings.environment.lower() == "development" and \
       settings.jwt_secret == "change-me-in-production-please":
        import warnings
        warnings.warn(
            "使用默认 JWT_SECRET，开发环境可接受但请勿用于生产！",
            RuntimeWarning,
        )

    if settings.vector_backend not in ("auto", "python", "pgvector"):
        raise RuntimeError("VECTOR_BACKEND 必须为 auto、python 或 pgvector")
    if settings.retrieval_mode not in ("hybrid", "vector", "lexical"):
        raise RuntimeError("RETRIEVAL_MODE 必须为 hybrid、vector 或 lexical")
    if settings.embedding_dim <= 0:
        raise RuntimeError("EMBEDDING_DIM 必须为正整数")
    if settings.hybrid_rrf_k <= 0 or settings.hybrid_candidate_k <= 0:
        raise RuntimeError("HYBRID_RRF_K 与 HYBRID_CANDIDATE_K 必须为正整数")

    if settings.environment.lower() != "production":
        return

    # 生产环境额外校验
    if "*" in cors_origin_list():
        raise RuntimeError("生产环境禁止使用 CORS 通配符")
