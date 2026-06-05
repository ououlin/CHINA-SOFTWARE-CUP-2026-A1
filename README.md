# 基于多模态大模型技术的设备检修知识检索与作业系统

> 第十五届中国软件杯 A 组赛题 · 龙芯中科出题

面向工业 / 制造业设备检修场景的 B/S 系统：融合**多模态知识检索、标准化作业指引、知识沉淀与知识图谱、大模型输出标注修正**四大能力，把分散的检修手册与一线经验沉淀为「可检索、可执行、可演进」的智能知识体系。

- 大模型走**云端 API**（DeepSeek 对话 + Qwen-VL 多模态），服务器无需 GPU；
- 向量检索用 **pgvector**（开发期 SQLite 抽象，生产 PostgreSQL），不引入重型中间件；
- 前端编译为静态文件、后端纯 Python 依赖——整体规避在 **LoongArch + 银河麒麟**上的架构兼容风险。

---

## 四大核心功能

### ① 多模态知识检索（M1 + M2）✅
- **文本问答**：query → 向量检索 Top-K → 引用溯源 → DeepSeek **流式**生成，答案句末带 `[序号]` 出处，UI 展示引用卡片与相似度。
- **故障图片问答**：上传图片 → **Qwen-VL** 看图输出结构化故障描述 → 跨模态对齐到文本检索 → 结合片段诊断。
- **设备型号过滤**：作为结构化条件叠加在向量检索之上，实现「语义 + 精确过滤」混合检索。

### ② 标准化作业指引（M3）✅
- **流程模板**：设备类型 × 检修等级 → 一组有序步骤，每步挂操作要点 / 风险提示 / 所需工具。
- **合规校验拦截**：必检项未勾选确认时，前端「下一步」禁用 + 后端二次校验返回 `422` 拦截缺项，双重保险。
- **个性化推送**：按设备类型 + 检修等级筛选模板；可由大模型依检索到的手册片段**生成流程草稿**，审核员校核后发布。
- 作业完成归档，「作业记录」可查审计闭环。

### ③ 知识沉淀与更新 + 知识图谱（M4）✅
- 一线人员提交检修案例 → **待审核**队列；审核员**采纳**后即触发：
  - 切块向量化入库（`source_type=case`），案例**立即可被 RAG 检索并作为引用**；
  - 大模型**抽取实体与关系**（设备 / 部件 / 故障 / 原因 / 措施）写入知识图谱表。
- **知识图谱可视化**：ECharts 力导向图，按 `(name, etype)` 去重让节点跨案例共享；点击节点溯源关联案例与相邻实体。

### ④ 大模型输出标注与修正（M5）✅
- 每条回答可**点赞 / 点踩 + 文字纠正**。
- **反馈增强闭环**：纠正沉淀为「修正知识」，其原问题经嵌入后召回——再遇相似问题时**作为权威依据优先注入**上下文；前端展示「⚡ 本回答已采纳 N 条人工修正」横幅。
- **治理**：「标注修正」页统计满意度与修正知识，审核员可下架 / 恢复不当纠正（下架即移出闭环）。

---

## 进度

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 | 骨架 + 登录 + 最小 RAG 链路 | ✅ 已端到端验证 |
| M2 | 多模态检索（Qwen-VL）+ 型号过滤 + PDF 手册导入 | ✅ 已端到端验证 |
| M3 | 标准化作业指引（模板 / 步骤 / 合规 / 个性化推送） | ✅ 已端到端验证 |
| M4 | 知识沉淀（上传-审核-入库-抽图谱）+ 知识图谱可视化 | ✅ 已端到端验证 |
| M5 | 大模型输出标注与修正（反馈增强闭环） | ✅ 已端到端验证 |
| M0 | 龙芯虚机依赖冒烟（pgvector 编译、Python 依赖） | ⏳ 待虚机到位 |
| M6 / M7 | 麒麟部署打磨 / 文档 + PPT + 演示视频 | ⏳ 进行中 |

> **四大核心功能已全部实现。**

---

## 技术栈

| 层 | 技术 | LoongArch / 麒麟可行性 |
|---|---|---|
| 前端 | Vue3 + Vite + Element Plus + ECharts | ✅ Windows 编译为静态文件，服务器仅托管 |
| Web | Nginx（反代 + 静态托管 + SSE 透传） | ✅ 麒麟官方源 |
| 后端 | Python + FastAPI + Uvicorn | ✅ 纯 Python 依赖 |
| 数据库 | 开发期 SQLite，生产 PostgreSQL + **pgvector** | ✅ pgvector 纯 C 扩展可编译 |
| 大模型 | DeepSeek（对话）/ **Qwen-VL**（多模态） | ✅ 仅需 HTTPS 出网 |
| Embedding | 本地 fastembed（BAAI/bge-small-zh）/ DashScope（生产） | ✅ 可插拔 provider |
| 知识图谱 | PostgreSQL 关系表 + ECharts，避开 Neo4j | ✅ |
| 鉴权 | JWT + pbkdf2（标准库，免原生依赖） | ✅ |

> 大模型、Embedding、VL 均抽象为可插拔 provider，切换云端 / 本地只改 `.env`。

---

## 角色与演示账号

| 账号 | 密码 | 角色 | 权限 |
|---|---|---|---|
| `worker` | `worker123` | 一线人员 | 问答、执行作业、提交案例、反馈纠正（仅见本人） |
| `auditor` | `auditor123` | 审核员 | + 审核案例 / 发布 SOP / 治理修正 / 导入手册 |
| `admin` | `admin123` | 管理员 | 全部权限 |

---

## 本地启动

### 1. 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 配置：复制 .env.example 为 .env，设置 DEEPSEEK_API_KEY（图片问答另需 DASHSCOPE_API_KEY）
copy .env.example .env
# 初始化数据库 + 种子数据（首次会下载本地嵌入模型，需联网一次）
.\.venv\Scripts\python.exe -m app.seed
# 启动
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

API 文档（Swagger）：http://127.0.0.1:8000/docs

### 2. 前端

```powershell
cd frontend
npm install
npm run dev
```

访问 http://127.0.0.1:5173 （开发期 `/api` 代理到 8000）。

> **图片问答演示**：聊天页点「故障图片」上传 `samples/fault_panel_overheat.png`（模拟过热报警面板）。
> **DashScope 端点**：国际站 Model Studio 账号须在 `.env` 设 `DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/...`，否则 401。

---

## 目录结构

```
backend/
  app/
    config.py              配置（可插拔 provider）
    db.py  models.py        数据库与 ORM（用户/文档/SOP/案例/知识图谱/反馈）
    schemas.py              Pydantic 请求响应模型
    auth.py                 鉴权（pbkdf2 + JWT + 角色）
    llm/                    LLM provider（DeepSeek，一次性 + 流式）
    embedding/              Embedding provider（local fastembed / dashscope）
    vl/                     视觉 provider（Qwen-VL，故障图片理解）
    rag/
      retriever.py          向量检索 + 设备型号结构化过滤
      pipeline.py           RAG 编排（检索 → 引用 → 反馈增强 → LLM）
      multimodal.py         图片 → VL 描述 → 文本检索 → 诊断
      sop_gen.py            依手册生成 SOP 草稿（M3）
      kg_extract.py         案例抽取知识图谱实体/关系（M4）
      feedback.py           反馈增强：召回相似问题的人工修正（M5）
    ingest.py               PDF / 文本 → 切块 → 向量化 → 入库
    kg_store.py             知识图谱实体去重 upsert + 关系落库
    routers/                auth / chat / documents / sop / cases / kg / feedback
    seed.py                 初始化数据（账号 + 种子手册/SOP/案例/图谱）
frontend/
  src/
    views/                  Login / Layout / Chat / Documents /
                            SOP / Cases / Graph / Feedback
    api.js  store.js  router.js
README.md
项目技术方案与整体规划.md     设计与选型详述（含 LoongArch 可行性）
```

---

## 部署目标

最终部署于 **LoongArch 架构 + 银河麒麟高级服务器版 V11/V10**。架构选型、可行性判断与数据模型详见 [`项目技术方案与整体规划.md`](项目技术方案与整体规划.md)。
