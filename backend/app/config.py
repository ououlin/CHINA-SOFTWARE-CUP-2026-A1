"""全局配置：从环境变量 / .env 读取（pydantic-settings）。

设计原则：LLM、Embedding、VL 均为可插拔 provider，
切换云端/本地只改环境变量，业务代码不变。
"""
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

    # ---- 鉴权 ----
    jwt_secret: str = "change-me-in-production-please"
    jwt_expire_minutes: int = 720
    jwt_algorithm: str = "HS256"

    # ---- 检索 ----
    retrieve_top_k: int = 4


settings = Settings()
