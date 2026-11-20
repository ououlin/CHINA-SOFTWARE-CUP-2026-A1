"""测试夹具配置。

- 使用 SQLite 内存数据库（StaticPool 共享连接，跨线程可见）
- Mock LLM / Embedding（不依赖外部 API，可离线运行）
- 三种角色（worker/auditor/admin）的认证 token
- 种子数据初始化
"""
import contextlib
import hashlib
import io
import os
import sys
import types
from pathlib import Path
from typing import Dict, Iterator, List

# ===== 1. 在导入 app 之前设置环境变量 =====
# JWT_SECRET 必须至少 32 字符
os.environ.setdefault("JWT_SECRET", "test-secret-please-do-not-use-in-production-32+chars-long")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("EMBEDDING_PROVIDER", "local")
os.environ.setdefault("EMBEDDING_DIM", "512")
os.environ.setdefault("LLM_PROVIDER", "deepseek")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-for-offline")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")  # 测试关闭限流
os.environ.setdefault("QUERY_REWRITE_ENABLED", "false")  # 关闭查询改写避免调 LLM
os.environ.setdefault("GRAPH_RAG_ENABLED", "true")
os.environ.setdefault("PARENT_CHILD_ENABLED", "false")

# ===== 2. 让 backend 目录可被 import =====
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 若 httpx 未安装，尝试从其他 Python 版本的用户站点包加载（TestClient 依赖）
try:
    import httpx  # noqa: F401
except ImportError:
    import glob
    for _candidate in glob.glob(
        os.path.expanduser(r"~\AppData\Roaming\Python\Python3*\site-packages")
    ):
        if Path(_candidate, "httpx", "__init__.py").exists():
            sys.path.insert(0, _candidate)
            break


# ===== 3. 为缺失的第三方依赖提供最小桩模块（离线运行） =====
def _ensure_stub(name: str, factory):
    """若 name 模块无法导入，则用 factory() 构造的桩模块顶替。"""
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = factory()


def _coerce(value: str, field_type):
    """把环境变量字符串转换为字段类型。"""
    try:
        if field_type is bool:
            return value.lower() in ("true", "1", "yes", "on")
        if field_type is int:
            return int(value)
        if field_type is float:
            return float(value)
    except (ValueError, TypeError):
        pass
    return value


def _make_pydantic_settings_stub():
    """pydantic-settings 桩：从环境变量读取字段值，行为对齐 BaseSettings。

    仅在未安装 pydantic-settings 时启用（如本地离线环境）；
    CI 环境装了真实包则不会触发。
    """
    from pydantic import BaseModel

    mod = types.ModuleType("pydantic_settings")

    class BaseSettings(BaseModel):
        """简化版 BaseSettings：仅从环境变量读取，不解析 .env 文件。"""

        model_config = {"extra": "ignore"}

        def __init__(self, **kwargs):
            cls = type(self)
            values = {}
            for field_name, field_type in getattr(cls, "__annotations__", {}).items():
                env_val = os.environ.get(field_name.upper())
                if env_val is not None:
                    values[field_name] = _coerce(env_val, field_type)
                else:
                    default = getattr(cls, field_name, None)
                    if default is not None:
                        values[field_name] = default
            values.update(kwargs)
            super().__init__(**values)

    def SettingsConfigDict(**kwargs):
        return {"extra": "ignore", **kwargs}

    mod.BaseSettings = BaseSettings
    mod.SettingsConfigDict = SettingsConfigDict
    return mod


_ensure_stub("pydantic_settings", _make_pydantic_settings_stub)


# ===== 4. 导入应用并替换数据库引擎（StaticPool 共享内存连接） =====
# 注意：先 import app 包，再 from app.main 取 fastapi 实例，
# 避免后续 import app.db 把局部变量 app 覆盖为模块对象
import app.db  # noqa: E402
import app.main  # noqa: E402
import app.seed  # noqa: E402
import app.routers.chat  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

# 创建使用 StaticPool 的内存引擎，确保跨线程共享同一数据库
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
TestSessionLocal = sessionmaker(
    bind=test_engine, autoflush=False, autocommit=False, future=True
)

# 替换 app.db 的引擎和会话工厂（get_db 通过模块命名空间查找 SessionLocal）
app.db.engine = test_engine
app.db.SessionLocal = TestSessionLocal

# 替换直接 from ..db import engine / SessionLocal 的模块
app.main.engine = test_engine
app.seed.engine = test_engine
app.seed.SessionLocal = TestSessionLocal
app.routers.chat.SessionLocal = TestSessionLocal


# ===== 5. Mock LLM 与 Embedding（避免调用外部 API） =====
from app.llm.base import LLMProvider  # noqa: E402
from app.embedding.base import EmbeddingProvider  # noqa: E402


class FakeLLM(LLMProvider):
    """测试用 LLM：返回固定文本，不调用任何外部 API。

    支持 ReAct 模式：当检测到 system prompt 含 "ReAct" 时，
    按轮次返回 Thought/Action/Action Input 格式的推理序列。
    """

    _react_round = 0

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        if "ReAct" in system_msg or "react" in system_msg.lower():
            return self._react_response(messages)
        # 非 ReAct 模式：返回固定文本
        return "这是测试用的固定回答：建议检查火花塞与气门间隙，并清洗化油器怠速油路。[1]"

    def _react_response(self, messages: List[Dict[str, str]]) -> str:
        # 检查是否已有 Observation（判断第几轮）
        has_obs = any("Observation:" in m.get("content", "") for m in messages if m["role"] == "user")
        if not has_obs:
            # 第一轮：调用 search_manual
            return (
                "Thought: 用户描述了故障现象，需要先检索手册了解可能原因\n"
                'Action: search_manual\n'
                'Action Input: {"query": "怠速不稳"}'
            )
        # 有1个Observation：调用 query_graph
        obs_count = sum(1 for m in messages if m["role"] == "user" and "Observation:" in m.get("content", ""))
        if obs_count == 1:
            return (
                "Thought: 手册提到了相关原因，需要查知识图谱确认因果链\n"
                'Action: query_graph\n'
                'Action Input: {"query": "怠速不稳"}'
            )
        # 有2个Observation：收束出报告
        return (
            "Thought: 证据充分，多源交叉验证完毕，生成诊断报告\n"
            "Action: FINISH\n"
            "Action Input: ## 故障现象研判\n怠速不稳是常见故障。\n\n"
            "## 可能原因分析\n- 化油器堵塞 [E1]\n- 火花塞积碳 [E2]\n\n"
            "## 推荐处理措施\n1. 清洗化油器怠速油路\n2. 更换火花塞并校正间隙\n\n"
            "## 诊断置信度\n中高（多源证据一致）"
        )

    def stream(self, messages: List[Dict[str, str]], temperature: float = 0.3) -> Iterator[str]:
        yield self.chat(messages, temperature)


class FakeEmbedder(EmbeddingProvider):
    """测试用 Embedder：基于文本哈希生成确定性 512 维向量，无需 fastembed。"""

    EMBED_DIM = 512

    def embed(self, texts: List[str]) -> List[List[float]]:
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            # 用哈希字节构造确定性向量，不同文本得到不同向量
            vec = [((h[i % 32] >> (i % 8)) & 1) * 0.1 - 0.05 for i in range(self.EMBED_DIM)]
            out.append(vec)
        return out

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


_fake_llm = FakeLLM()
_fake_embedder = FakeEmbedder()

# 在所有已加载的 app 子模块中替换 get_llm / get_embedder 引用
# （模块内 from ..llm import get_llm 会绑定本地引用，需逐一替换）
for _mod_name, _mod in list(sys.modules.items()):
    if not _mod_name.startswith("app.") or _mod is None:
        continue
    _mod_dict = getattr(_mod, "__dict__", {})
    if "get_llm" in _mod_dict:
        _mod_dict["get_llm"] = lambda _f=_fake_llm: _f
    if "get_embedder" in _mod_dict:
        _mod_dict["get_embedder"] = lambda _f=_fake_embedder: _f


# ===== 6. 建表 + 种子数据初始化 =====
app.db.Base.metadata.create_all(bind=test_engine)

# 运行种子数据初始化（抑制 print 输出）
with contextlib.redirect_stdout(io.StringIO()):
    app.seed.run()


# ===== 7. Pytest 夹具定义 =====
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """会话级 TestClient，触发 lifespan 建表。"""
    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture(scope="function")
def db_session():
    """函数级数据库会话（用于查询/验证测试数据）。"""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _login(client: TestClient, username: str, password: str) -> str:
    """登录并返回 access_token。"""
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def worker_token(client: TestClient) -> str:
    """一线人员 token。"""
    return _login(client, "worker", "worker123")


@pytest.fixture(scope="session")
def auditor_token(client: TestClient) -> str:
    """审核员 token。"""
    return _login(client, "auditor", "auditor123")


@pytest.fixture(scope="session")
def admin_token(client: TestClient) -> str:
    """管理员 token。"""
    return _login(client, "admin", "admin123")


@pytest.fixture(scope="session")
def worker_headers(worker_token: str) -> dict:
    """一线人员认证头。"""
    return _auth_header(worker_token)


@pytest.fixture(scope="session")
def auditor_headers(auditor_token: str) -> dict:
    """审核员认证头。"""
    return _auth_header(auditor_token)


@pytest.fixture(scope="session")
def admin_headers(admin_token: str) -> dict:
    """管理员认证头。"""
    return _auth_header(admin_token)
