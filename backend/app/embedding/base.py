"""Embedding 抽象接口。所有实现需返回等长 float 向量列表。"""
from abc import ABC, abstractmethod
from typing import List


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """批量文本 -> 向量。"""
        raise NotImplementedError

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]
