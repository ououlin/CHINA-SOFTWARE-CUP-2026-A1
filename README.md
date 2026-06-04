# 基于多模态大模型技术的设备检修知识检索与作业系统

第十五届中国软件杯 A 组赛题 · 龙芯中科。
B/S 架构，面向工业/制造业设备检修，提供多模态知识检索、标准化作业指引、知识沉淀与大模型输出修正。

## 当前进度：M1 + M2

### M1（骨架 + 登录 + 最小 RAG 链路）✅
- ✅ 前后端项目骨架
- ✅ 登录 / JWT 鉴权 / 角色（一线、审核、管理）
- ✅ 文本问答 RAG 链路（向量检索 → 引用溯源 → DeepSeek 流式生成）
- ✅ 可插拔 LLM / Embedding provider（云端 DeepSeek + 本地 fastembed，可切 Qwen）

### M2（多模态检索 + 知识导入）✅ 已端到端验证（含真实 Qwen-VL）
- ✅ 故障图片问答：上传图片 → Qwen-VL 看图提取故障描述 → 跨模态对齐到文本检索 → DeepSeek 诊断
- ✅ 设备型号结构化过滤（语义 + 精确过滤混合检索）
- ✅ PDF 检修手册导入：解析 → 切块 → 向量化 → 入库（审核员/管理员，无需 VL Key）
- ⏳ M3 标准化作业指引、M4 知识沉淀与审核、M5 标注修正

> **测试图片问答**：聊天页点「故障图片」上传 `samples/fault_panel_overheat.png`（模拟过热报警面板）即可看到完整诊断。
>
> **DashScope 端点**：国内站 / 国际站按账号开通地区在 `.env` 设 `DASHSCOPE_BASE_URL`（国际站 Model Studio 账号必须用 `dashscope-intl.aliyuncs.com`，否则 401）。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue3 + Vite + Element Plus + ECharts |
| 后端 | Python FastAPI |
| 数据库 | 开发期 SQLite（生产 PostgreSQL + pgvector） |
| 大模型 | DeepSeek（对话）/ Qwen-VL（多模态，规划中） |
| Embedding | 本地 fastembed（开发）/ DashScope（生产） |

> 部署目标：LoongArch 架构 + 银河麒麟高级服务器版 V11/V10。详见 `项目技术方案与整体规划.md`。

## 本地启动

### 1. 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 配置环境：复制 .env.example 为 .env，确保 DEEPSEEK_API_KEY 已设置（或用系统环境变量）
copy .env.example .env
# 初始化数据库 + 种子数据（首次会下载本地嵌入模型，需联网一次）
.\.venv\Scripts\python.exe -m app.seed
# 启动
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

API 文档：http://127.0.0.1:8000/docs

### 2. 前端

```powershell
cd frontend
npm install
npm run dev
```

访问：http://127.0.0.1:5173 ，演示账号 `worker / worker123`。

## 目录结构

```
backend/
  app/
    config.py          配置（可插拔 provider）
    db.py models.py     数据库与 ORM
    auth.py             鉴权（pbkdf2 + JWT）
    llm/                LLM provider（DeepSeek）
    embedding/          Embedding provider（local / dashscope）
    vl/                 视觉模型 provider（Qwen-VL，故障图片理解）
    rag/                检索 + RAG 编排 + 多模态(multimodal.py)
    ingest.py           PDF 解析 → 切块 → 向量化 → 入库
    routers/            auth / chat / documents 路由
    seed.py             初始化数据
frontend/
  src/
    views/              Login / Layout / Chat / Documents
    api.js store.js router.js
项目技术方案与整体规划.md
```
