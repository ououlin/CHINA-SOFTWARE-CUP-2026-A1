"""DeepSeek 对话模型（OpenAI 兼容协议）。

仅做文本对话生成。注意：DeepSeek 无 Embedding、无视觉能力，
故 Embedding 见 app/embedding，多模态(M2)将另接 Qwen-VL。
"""
import json
from typing import Iterator, List, Dict

import httpx

from ..config import settings
from .base import LLMProvider


class DeepSeekLLM(LLMProvider):
    def __init__(self):
        if not settings.deepseek_api_key:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY")
        self._url = settings.deepseek_base_url.rstrip("/") + "/v1/chat/completions"
        self._model = settings.deepseek_model
        self._headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
        resp = httpx.post(
            self._url, headers=self._headers,
            json={"model": self._model, "messages": messages,
                  "temperature": temperature, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def stream(self, messages: List[Dict[str, str]],
               temperature: float = 0.3) -> Iterator[str]:
        with httpx.stream(
            "POST", self._url, headers=self._headers,
            json={"model": self._model, "messages": messages,
                  "temperature": temperature, "stream": True},
            timeout=120,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"]
                    piece = delta.get("content")
                    if piece:
                        yield piece
                except Exception:
                    continue
