"""VL 抽象接口：输入图片字节 + 文本提示，返回理解后的文本。"""
from abc import ABC, abstractmethod


class VLProvider(ABC):
    @abstractmethod
    def understand(self, image_bytes: bytes, prompt: str,
                   mime: str = "image/jpeg") -> str:
        """看图 + 提示词 -> 文本描述。"""
        raise NotImplementedError
