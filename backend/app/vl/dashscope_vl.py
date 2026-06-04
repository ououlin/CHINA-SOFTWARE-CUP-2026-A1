"""Qwen-VL（阿里云 DashScope，OpenAI 兼容多模态协议）。

用于故障图片理解：识别设备/部件、可见故障现象、提取故障关键词。
需配置 DASHSCOPE_API_KEY。
"""
import base64
from typing import List, Dict

import httpx

from ..config import settings
from .base import VLProvider


class DashScopeVL(VLProvider):
    def __init__(self):
        if not settings.dashscope_api_key:
            raise RuntimeError(
                "故障图片理解需要 Qwen-VL：请配置 DASHSCOPE_API_KEY "
                "（DeepSeek 不支持图像，详见部署文档）"
            )
        self._url = settings.dashscope_base_url.rstrip("/") + "/chat/completions"
        self._model = settings.dashscope_vl_model
        self._headers = {
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

    def understand(self, image_bytes: bytes, prompt: str,
                   mime: str = "image/jpeg") -> str:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        messages: List[Dict] = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }]
        resp = httpx.post(
            self._url, headers=self._headers,
            json={"model": self._model, "messages": messages,
                  "temperature": 0.2},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
