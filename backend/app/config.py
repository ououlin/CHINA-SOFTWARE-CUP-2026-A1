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
    query_rewrite_enabled: bool = True   # 进阶：检索前把口语 query 改写为工业术语
    graph_rag_enabled: bool = True       # 进阶：Graph RAG，注入知识图谱邻居作结构化上下文
    parent_child_enabled: bool = True    # 进阶：父子分块，召回子块、喂模型父块上下文
    parent_window: int = 1               # 父块向同文档相邻各扩展的块数

    # ---- 接口限流（进阶，保护云端 API 额度）----
    rate_limit_enabled: bool = True
    rate_limit_chat: int = 20            # 每用户每分钟问答次数（审核员/管理员 ×3）
    rate_limit_upload: int = 10          # 每用户每分钟图片/上传次数（审核员/管理员 ×3）

    # ---- 离线/局域网模式（进阶预案）----
    # 标识离线部署；LLM/VL 实际切换由 deepseek_base_url / dashscope_base_url 指向
    # 局域网 Ollama/vLLM（OpenAI 兼容），Embedding 切本地 fastembed，均只改 .env
    offline_mode: bool = False


settings = Settings()
