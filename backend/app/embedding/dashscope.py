"""云端 Embedding（阿里云 DashScope / Qwen text-embedding-v3）。

生产推荐：无需本地模型，规避 LoongArch 上 ONNX/torch 兼容问题。
需配置 DASHSCOPE_API_KEY。OpenAI 兼容协议。
"""
from typing import List

import httpx

from ..config import settings
from .base import EmbeddingProvider


class DashScopeEmbedding(EmbeddingProvider):
    def __init__(self):
        if not settings.dashscope_api_key:
            raise RuntimeError("EMBEDDING_PROVIDER=dashscope 需要配置 DASHSCOPE_API_KEY")
        self._url = settings.dashscope_base_url.rstrip("/") + "/embeddings"
        self._model = settings.dashscope_embedding_model
        self._headers = {
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        resp = httpx.post(
            self._url,
            headers=self._headers,
            json={"model": self._model, "input": texts},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        data.sort(key=lambda x: x["index"])
        return [item["embedding"] for item in data]
