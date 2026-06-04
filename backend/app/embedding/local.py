"""本地 Embedding（fastembed / ONNX，CPU，零 Key）。

开发期默认实现。模型首次使用会自动下载（需联网一次）。
注意：生产部署到 LoongArch 时，onnxruntime 的可用性需在龙芯虚机实测，
若不可用则切换 EMBEDDING_PROVIDER=dashscope 使用云端嵌入。
"""
from typing import List

from ..config import settings
from .base import EmbeddingProvider


class LocalEmbedding(EmbeddingProvider):
    def __init__(self):
        from fastembed import TextEmbedding
        self._model = TextEmbedding(model_name=settings.embedding_model)

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        # fastembed 返回 numpy 生成器
        return [vec.tolist() for vec in self._model.embed(texts)]
