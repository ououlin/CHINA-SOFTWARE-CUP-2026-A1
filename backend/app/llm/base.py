"""LLM 抽象接口：支持一次性与流式两种生成。"""
from abc import ABC, abstractmethod
from typing import Iterator, List, Dict


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
        """一次性返回完整回答。"""
        raise NotImplementedError

    @abstractmethod
    def stream(self, messages: List[Dict[str, str]],
               temperature: float = 0.3) -> Iterator[str]:
        """流式返回增量文本片段。"""
        raise NotImplementedError
