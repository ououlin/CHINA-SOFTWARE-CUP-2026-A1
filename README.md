# 设备检修知识检索与作业系统

> **多模态 RAG · ReAct 自主诊断 Agent · 知识治理闭环 · 国产化可部署**<br/>
> 第十五届中国软件杯 A 组赛题 · 龙芯中科出题

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-42B883?logo=vuedotjs&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-336791?logo=postgresql&logoColor=white)
![LoongArch](https://img.shields.io/badge/LoongArch-%E9%93%B6%E6%B2%B3%E9%BA%92%E9%BA%9F-C8102E)

面向工业及制造业设备检修场景的 B/S 智能知识系统。把分散在手册、案例和一线经验里的检修知识，沉淀为**可检索、可执行、可追溯、可演进**的一体化知识体系：工人问一句「发动机怠速不稳」，系统检索手册与同类案例、按知识图谱交叉验证、逐条给出引用，再由 ReAct Agent 自主决定是否补检索，最终输出可执行的诊断报告与标准作业步骤。

- **大模型走云端 API**（DeepSeek 对话 + Qwen-VL 多模态），服务器无需 GPU
- **向量检索用 pgvector**（开发期 SQLite 回退），pg_trgm 字面召回 + RRF 融合，不引入重型中间件
- **前端预编译为静态文件**，后端优先纯 Python 依赖，并附 LoongArch + 银河麒麟实机证据采集工具

---

## 目录

- [功能总览](#功能总览)
- [核心创新一：ReAct 自主诊断引擎（G9）](#核心创新一react-自主诊断引擎g9)
- [核心创新二：知识图谱推理链与故障树（G10）](#核心创新二知识图谱推理链与故障树g10)
- [技术架构](#技术架构)
- [快速开始](#快速开始)
- [关键配置](#关键配置)
- [部署](#部署)
- [测试与评测](#测试与评测)
- [演示指南](#演示指南)
- [种子数据](#种子数据)
- [目录结构](#目录结构)
- [文档索引](#文档索引)
- [已知边界与口径](#已知边界与口径)

---

## 功能总览

### 四大核心能力（对应赛题 M1–M5）

| 模块 | 能力 | 实现要点 |
|---|---|---|
| **M1 多模态知识检索** | 文本问答 + 引用溯源 | query → 混合召回 Top-K → DeepSeek 流式生成，答案句末带 `[序号]`，UI 展示引用卡片与相似度 |
| **M2 故障图片问答** | 图片 → 结构化故障描述 → 跨模态检索 | Qwen-VL 看图输出故障描述，VL 判定非工业故障或置信度低于阈值时直接拦截，避免「一本正经地胡编」 |
| **M3 标准化作业指引** | 流程模板 + 合规校验 + 个性化推送 | 设备类型 × 检修等级 → 有序步骤（要点/风险/工具）；必检项未完成时前端禁用「下一步」、后端返回 `422` 二次拦截；可由手册片段生成流程草稿，审核后发布 |
| **M4 知识沉淀与图谱** | 案例审核 → 向量入库 → 实体关系抽取 | 审核采纳即触发切块向量化（`source_type=case`，立即可被 RAG 引用）与实体/关系落库；ECharts 力导向图按 `(name, etype)` 去重共享节点 |
| **M5 标注修正闭环** | 点赞/点踩 + 文字纠正 → 权威依据 | 纠正沉淀为「修正知识」，再遇相似问题时优先注入上下文；审核员可下架/恢复不当纠正，下架即移出闭环 |

### 增强能力（G1–G13）

| # | 能力 | 要点 |
|---|---|---|
| G1 | 设备健康档案（一机一档） | 台账 + 报修/维修时间线（精确挂设备）+ 同型号案例与适用 SOP 软关联；报修自动流转设备状态 |
| G2 | 数据驾驶舱 | 登录首页：8 项指标 + 设备状态/高故障设备/图谱分布 + 近 7 天问答与报修趋势（6 组 ECharts） |
| G3 | 多轮对话 | 上下文记忆，对「它 / 这个故障」等追问做指代补全后再检索 |
| G4 | 语音问答 | 浏览器原生 Web Speech API，现场免手输；不支持时降级提示 |
| G5 | 智能检修报告 | LLM 汇总台账与报修时间线，生成结构化《检修报告》，可导出 Markdown |
| G6 | 故障预警 · 预测性维护 | 规则化风险评分（可解释）识别高风险设备与高频故障，LLM 生成维护建议 |
| G7 | 扫码报修 | 每台设备生成二维码（可打印张贴），扫码或输入编号即调档报修 |
| G8 | 检索重排 | 向量召回后混合重排（语义 + 字面词项重叠），引用卡展示「综合·语义·字面」三分 |
| **G9** | **ReAct 自主诊断引擎** | Thought → Action → Observation 自主循环，Agent 依据中间结果决定下一步，详见下文 |
| **G10** | **图谱推理链 + 故障树（FTA）** | 3 跳推理、可信度按 0.85^n 衰减、自动构建 FTA 树并可视化 |
| G11 | 前端体验优化 | 暗色主题、响应式布局、骨架屏、SSE 断线重连、空状态引导 |
| **G12** | **证据冲突检测** | 多源证据矛盾时标注 `[冲突]` 并给出消解策略（优先采信最新案例与设备维修记录） |
| **G13** | **Agent 诊断可视化** | SSE 实时推送 Thought 时间线、Action 工具卡片、推理链 Sankey、FTA 树与报告 Markdown 渲染 |

> 全部增强能力复用既有云端 API / 纯 Python / 前端预编译方案，**不向 LoongArch 引入新的编译风险**。

---

## 核心创新一：ReAct 自主诊断引擎（G9）

传统 RAG 是「一次检索 → 一次生成」，推理过程不可观测；固定流水线式 Agent 步骤写死，无法依据中间结果调整策略。本实现把诊断建模为 **Reasoning + Acting 循环**，像专家一样「分析 → 查证 → 再分析 → 再查证 → 出报告」：

```
用户：发动机怠速不稳，冷车易熄火
  │
  ▼ Thought 1  描述了怠速不稳与冷车熄火，先检索手册确认可能原因
  ▼ Action 1   search_manual("发动机怠速不稳 冷车熄火")
  ▼ Observation 1   [E1] 化油器怠速油路堵塞… [E2] 火花塞积碳…
  │
  ▼ Thought 2  手册指向化油器与火花塞，查图谱确认因果链
  ▼ Action 2   query_graph("怠速不稳")
  ▼ Observation 2   推理链：怠速不稳 → 化油器堵塞 → 清洗化油器
  │
  ▼ Thought 3  图谱链路成立，再找同类案例佐证
  ▼ Action 3   search_case("怠速不稳 化油器")
  ▼ Observation 3   [E4] 同类案例实测为阻风门膜片破裂…
  │
  ▼ Thought 4  三源交叉验证充分
  ▼ Action 4   FINISH → 结构化诊断报告（Markdown）
```

**工具集**（Agent 自主选择，不按固定顺序调用）：

| 工具 | 作用 | 返回 |
|---|---|---|
| `search_manual` | 检索检修手册片段 | Top-3 片段 + 相似度 |
| `search_case` | 检索已采纳检修案例 | Top-3 案例 |
| `query_graph` | 查询图谱推理链 | 故障 → 原因 → 措施链路 + 关联三元组 |
| `query_device_history` | 查询设备维修历史 | 台账 + 最近维修记录 |

**工程约束**（均在 `backend/app/config.py` 可配）：

- `AGENT_MAX_ITERATIONS=8`：最大推理轮数；`AGENT_MIN_DISTINCT_TOOLS=2`：至少两类工具后才允许收束
- `AGENT_PARSE_RETRIES=1`：动作 JSON 解析失败重试；`AGENT_TOOL_BUDGET_SECONDS=15`：单次工具超时预算
- Pydantic 校验 Action 协议，解析异常/工具失败降级为兜底回答，不中断会话
- 证据冲突时标注 `[冲突]`（G12），并在报告中给出采信倾向

**接口**：`POST /api/chat/diagnose`（非流式）、`POST /api/chat/diagnose_stream`（SSE 逐步推送）。

---

## 核心创新二：知识图谱推理链与故障树（G10）

**多跳推理**：从故障实体出发沿「源于 → 采取」关系做 3 跳 BFS，每跳可信度乘 0.85 衰减：

```
fault → cause → sub_cause → root_cause
["主轴异响", "轴承磨损", "滚道剥落"]  → 0.85² ≈ 0.72
```

**故障树（FTA）**：自动构建层次化原因树，节点携带可信度与对应措施：

```
发动机过热 (fault, 1.00)
├─ 散热片堵塞 (cause, 0.85)
│   └─ 长期未保养 (cause, 0.72)  措施：清理散热片、定期保养
├─ 机油不足 (cause, 0.85)        措施：补充机油
└─ 点火过迟 (cause, 0.85)        措施：校正点火正时
```

**接口**：`GET /api/kg/reasoning?query=…`、`GET /api/kg/reasoning_confidence?query=…`、`GET /api/kg/fault_tree?query=…&max_depth=3`。

**前端**：推理链 → ECharts Sankey；故障树 → ECharts tree（可展开/折叠、显示可信度）。

> 口径说明：0.85^n 是固定衰减系数，属于**可解释评分**而非统计置信度；完成标注校准前不宣称其概率含义（见 [docs/national-special-roadmap.md](docs/national-special-roadmap.md)）。

---

## 技术架构

```
浏览器 ──HTTP / SSE──▶ Nginx ──┬── 静态资源（frontend/dist，开发机预编译）
                                └── /api 反代 ──▶ Gunicorn + Uvicorn（FastAPI）
                                                      ├──▶ PostgreSQL + pgvector / pg_trgm
                                                      └──HTTPS──▶ 云端模型（DeepSeek / DashScope）
```

| 层 | 选型 | 国产化考量 |
|---|---|---|
| 前端 | Vue 3 + Vite + Element Plus + ECharts | 开发机预编译静态文件，服务器只托管，无运行时编译 |
| Web 服务 | Nginx（静态 + 反代 + SSE 透传） | 银河麒麟官方源自带 |
| 后端 | Python 3.12 + FastAPI + Uvicorn | 纯 Python 主体，无可选 C 扩展硬依赖 |
| 数据库 | 开发 SQLite / 生产 PostgreSQL + pgvector + pg_trgm | 向量与字面召回都在库内完成，SQLite 仅作演示回退 |
| 大模型 | DeepSeek（对话）、Qwen-VL（多模态） | 仅需 HTTPS 出网，可切局域网 OpenAI 兼容服务 |
| Embedding | 本地 fastembed（开发）/ DashScope（生产） | provider 可插拔，生产不装 onnxruntime |
| 知识图谱 | PostgreSQL 关系表 + ECharts（不引入 Neo4j） | 少一个中间件，备份恢复链路更短 |
| 鉴权 | JWT + 标准库 pbkdf2 | 免 bcrypt 原生依赖 |
| 可观测性 | Prometheus 指标端点 `/metrics`、操作审计日志 | — |

**检索策略**：`RETRIEVAL_MODE=hybrid|vector|lexical`，`VECTOR_BACKEND=auto|python|pgvector`。hybrid 模式下 pgvector 向量召回与 pg_trgm 字面召回各取候选（`HYBRID_CANDIDATE_K=50`），以 RRF（`HYBRID_RRF_K=60`）融合后取 `RETRIEVE_TOP_K=4`；pgvector 不可用时自动回退应用层检索。

**Provider 抽象**：LLM / Embedding / VL 均通过 `get_llm()`、`get_embedding()`、`get_vl()` 工厂切换，云端、局域网 Ollama/vLLM、本地模型只改 `.env`，业务代码不动。

---

## 快速开始

### 环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | 3.12（CI 基准，3.11 实测可用） | 后端与测试 |
| Node.js | 20+ | 前端构建 |
| PostgreSQL | 16 + pgvector（可选） | 生产检索；本地默认 SQLite |
| Docker | 24+（可选） | 一条命令起前后端 |

### 后端

```bash
cd backend
python -m venv .venv

# 激活或用绝对路径调用：Linux/macOS 为 .venv/bin/python，Windows 为 .venv\Scripts\python.exe
.venv/bin/python -m pip install -r requirements.txt

cp .env.example .env            # 填入 DEEPSEEK_API_KEY；图片问答另需 DASHSCOPE_API_KEY
# JWT_SECRET 必须 ≥ 32 字符，否则应用启动即拒绝（见 app/config.py）

.venv/bin/python -m app.seed    # 初始化数据库与种子数据（首次会下载本地嵌入模型，需联网一次）
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

- 健康检查：<http://127.0.0.1:8000/api/health> → `{"status":"ok","stage":"M5+"}`
- 接口文档：<http://127.0.0.1:8000/docs>

### 前端

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173 ，开发期 /api 代理到 8000
npm run build      # 产物在 dist/，部署时整体上传
```

> **图片问答验证**：聊天页点击「故障图片」，上传 `samples/fault_panel_overheat.png` 即可体验多模态链路。
> **DashScope 国际站**：使用百炼国际站账号时，需把 `DASHSCOPE_BASE_URL` 改为 `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`，否则返回 401。

### 演示账号

| 账号 | 密码 | 角色 | 权限 |
|---|---|---|---|
| `worker` | `worker123` | 一线人员 | 问答、执行作业、提交案例、反馈纠正 |
| `auditor` | `auditor123` | 审核员 | + 审核案例 / 发布 SOP / 治理修正 / 导入手册 |
| `admin` | `admin123` | 管理员 | 全部权限 |

---

## 关键配置

完整模板见 [`backend/.env.example`](backend/.env.example)，生产模板见 [`deploy/.env.production.example`](deploy/.env.production.example)。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` | 空 / `deepseek-chat` | 对话模型 |
| `DASHSCOPE_API_KEY` / `DASHSCOPE_VL_MODEL` | 空 / `qwen-vl-max` | 多模态与云端 Embedding |
| `EMBEDDING_PROVIDER` | `local` | `local`（fastembed）或 `dashscope` |
| `EMBEDDING_DIM` | `512` | 须与所选嵌入模型一致，pgvector 建索引依赖该值 |
| `DATABASE_URL` | `sqlite:///./app.db` | 生产：`postgresql+pg8000://user:pwd@host:5432/db` |
| `RETRIEVAL_MODE` | `hybrid` | `hybrid` / `vector` / `lexical` |
| `VECTOR_BACKEND` | `auto` | `auto` / `python` / `pgvector` |
| `JWT_SECRET` | 无（必填） | ≥ 32 字符；生产环境还会拒绝 CORS 通配符 |
| `AGENT_MAX_ITERATIONS` | `8` | Agent 最大推理轮数 |
| `RATE_LIMIT_CHAT` / `RATE_LIMIT_UPLOAD` | `20` / `10` | 每用户每分钟问答/上传次数（审核员、管理员 ×3） |
| `IMAGE_CONFIDENCE_THRESHOLD` | `0.6` | VL 判别置信度下限，低于即拦截 |
| `OFFLINE_MODE` | `false` | 离线部署标识（仅标识，模型切换看 Base URL） |

---

## 部署

### 方式一：Docker Compose（最快）

```bash
cp backend/.env.example backend/.env     # 至少填 DEEPSEEK_API_KEY / JWT_SECRET
docker compose up -d --build             # 前端 :80，后端 :8000
```

| 文件 | 作用 |
|---|---|
| `backend/Dockerfile` | python:3.12-slim + 编译工具 + PyMuPDF 系统库 + 健康检查 |
| `frontend/Dockerfile` | 多阶段：node:20-alpine 构建 → nginx:alpine 托管 |
| `frontend/nginx.conf` | SPA 路由回退 + `/api` 反代 + SSE 透传 + gzip |
| `docker-compose.yml` | backend + frontend 编排，数据卷持久化 DB / 上传 / 模型缓存 |
| `docker-compose.pgvector.yml` | 追加 PostgreSQL + pgvector 服务，用于检索压测与集成验证 |

### 方式二：LoongArch + 银河麒麟一键部署

**① 开发机构建前端**：`cd frontend && npm run build`，把 `dist/` 上传到服务器 `/opt/device-repair/frontend/dist`。

**② 服务器准备代码**：

```bash
sudo dnf install -y git          # 或 yum
sudo git clone https://github.com/ououlin/CHINA-SOFTWARE-CUP-2026-A1.git /opt/device-repair
cd /opt/device-repair
```

**③ 填写密钥**：`cp deploy/.env.production.example backend/.env`，按上表填写 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY`、`DATABASE_URL`、`JWT_SECRET`。

**④ 一键部署**：

```bash
bash deploy/00_smoke_test.sh     # 部署前依赖体检（不改动系统，只出通过/失败清单）
sudo bash deploy/deploy.sh
```

`deploy.sh` 依次完成：系统依赖 → PostgreSQL 库与 pgvector 扩展/索引（缺失时调用 `02_install_pgvector.sh`）→ 后端 venv、依赖、种子、systemd → Nginx 与 SELinux/防火墙。完成后访问 `http://<服务器IP>/`。

**LoongArch 兼容性风险与规避**：

| 风险点 | 规避方案 |
|---|---|
| fastembed / onnxruntime 在龙芯缺 wheel | 生产设 `EMBEDDING_PROVIDER=dashscope`，服务器不装 onnxruntime |
| psycopg2 需 libpq 编译 | 改用纯 Python 驱动 `pg8000` |
| `uvicorn[standard]` 含 uvloop/httptools C 扩展 | 用纯净版 uvicorn，性能以实机压测为准 |
| PyMuPDF 含 C 扩展 | 延迟导入，装不上只损失 PDF 上传，不影响启动 |
| pgvector 需源码编译 | 生产必须编译安装并保留记录；SQLite/应用层检索只作回退 |
| pydantic-core 需 Rust 工具链 | 无 wheel 时安装 rust/cargo 源码编译并保留日志 |

**常用排查**：

```bash
sudo dnf install -y rust cargo                                   # pydantic-core 编译失败
sudo setsebool -P httpd_can_network_connect 1                    # Nginx 502（SELinux）
grep -n "proxy_buffering" /etc/nginx/conf.d/device-repair.conf   # SSE 被缓冲
systemctl status device-repair-backend nginx && journalctl -u device-repair-backend -n 50
```

### 方式三：离线 / 保密局域网

所有 provider 已抽象，切换只改 `.env`：

| 组件 | 离线方案 | 配置 |
|---|---|---|
| 对话 LLM | 内网 Ollama / vLLM（OpenAI 兼容） | `DEEPSEEK_BASE_URL=http://<内网IP>:11434/v1`、`DEEPSEEK_MODEL=qwen2.5` |
| 多模态 VL | 内网 Qwen-VL（OpenAI 兼容） | `DASHSCOPE_BASE_URL=http://<内网IP>:.../v1` |
| Embedding | 本地 fastembed 或内网嵌入服务 | `EMBEDDING_PROVIDER=local` |
| 标识 | `OFFLINE_MODE=true` | 仅作部署标识 |

> 完全离线要求对话、VL、Embedding 三者都有内网服务；只设 `OFFLINE_MODE=true` 并不能让云端调用消失。

### 运维

```bash
sudo systemctl restart device-repair-backend      # 重启后端
cd /opt/device-repair && sudo git pull            # 更新代码后重跑 deploy.sh

bash deploy/04_backup_restore.sh backup           # pg_dump 到 evidence/backups，附 sha256 与内容清单
RESTORE_DATABASE_URL=postgresql://user:pwd@127.0.0.1:5432/restore_db \
  bash deploy/04_backup_restore.sh verify <备份文件>
```

---

## 测试与评测

### 自动化测试

```bash
cd backend
.venv/bin/python -m pytest -q
```

覆盖鉴权与越权、文本/图片/SSE 问答、Agent 协议与失败降级、三种检索模式、pgvector 合同、知识安全（注入/投毒）、图谱来源治理、SOP、案例、设备与反馈闭环。最近一次本地回归（Python 3.11 + SQLite）：**66 passed, 1 skipped**；跳过项为需要真实 PostgreSQL 的 pgvector 集成用例，未提供 `TEST_POSTGRES_URL` 时自动跳过，CI 中由 pgvector 服务容器兜底。

### 量化评测与证据

```bash
cd backend
python -m evaluation.evaluate_retrieval --fail-on-threshold     # Recall/MRR/nDCG
python -m evaluation.evaluate_ablation  --fail-on-threshold     # 三模式消融
python -m evaluation.evaluate_agent     --fail-on-threshold     # 任务完成率 / 引用有效性
python -m evaluation.load_test --mode health --concurrency 30 --requests 30 --fail-on-threshold
python -m evaluation.load_test --mode sse --concurrency 30 --requests 30

cd ..
python deploy/generate_sbom.py --output evidence/sbom/cyclonedx.json   # CycloneDX SBOM
bash deploy/05_collect_loongarch_evidence.sh                           # 实机 8 小时稳定性证据
```

报告默认写入仓库根目录 `evidence/`（`evaluation/`、`performance/` 等，按时间戳分目录）。**该目录是运行产物，不随仓库提交**；答辩时以实机跑出的报告为准，未经实测的数字不写成结论。

### 持续集成

`.github/workflows/ci.yml` 在 push / PR 时并行执行两个作业：

| 作业 | 步骤 |
|---|---|
| Backend Check | Python 3.12 → 安装依赖 → `py_compile` 全量语法检查 → `ruff check`（E9/F63/F7/F82，阻断未定义名与语法错误）→ `pytest`（挂载 pgvector/pg16 服务） |
| Frontend Build | Node 20 → `npm ci` → `npm run build` |

同分支新提交自动取消旧流水线（`concurrency.cancel-in-progress`）。

---

## 演示指南

### 推荐故障样本（种子数据可完整触发 ReAct 链路）

| # | 故障描述 | 设备类型 | 推理链路 | 预期工具序列 |
|---|---|---|---|---|
| 1 | 发动机怠速不稳，冷车易熄火 | 摩托车发动机 | 怠速不稳 → 化油器堵塞 → 清洗化油器 | search_manual → query_graph → search_case |
| 2 | 发动机过热怎么处理 | 摩托车发动机 | 发动机过热 → 散热片堵塞 → 清理散热片 | search_manual → query_graph |
| 3 | 螺杆空压机排气压力不足 | 螺杆空压机 | 排气压力不足 → 进气阀卡滞 → 清洗进气阀 | search_manual → query_graph → search_case |
| 4 | 数控车床主轴异响 | 数控机床 | 主轴异响 → 轴承磨损 → 滚道剥落 | search_manual → query_graph → query_device_history |
| 5 | 数控车床 X 轴反向间隙过大 | 数控机床 | 反向间隙过大 → 预紧失效 → 碟簧损坏 | search_manual → query_graph |

### 五分钟主演示

1. **登录 + 数据看板**（`worker/worker123`）→ 指标卡、设备状态、图谱分布与 7 天趋势（G2）
2. **多模态问答** → 输入「发动机过热」，展示流式回答与引用溯源卡片（M1）
3. **Agent 自主诊断** → 输入「发动机怠速不稳，冷车易熄火」，观察 Thought 时间线、工具卡片、Sankey 推理链、FTA 树与诊断报告（G9/G13）
4. **知识图谱** → 力导向图展示 70+ 实体，点击节点溯源关联案例（M4）
5. **反馈闭环** → 对回答点踩并提交纠正，再问相似问题，观察「本轮已采纳 N 条人工修正」（M5）

更细的 4 分钟脚本与追问库见 [docs/demo-4min-script.md](docs/demo-4min-script.md)、[docs/defense-qa.md](docs/defense-qa.md)。

### 兜底方案

- Agent 因模型输出格式偏差中断：普通问答（`/chat`）不受影响，继续演示检索与引用
- 切换知识图谱页直接演示推理链与故障树（不依赖 Agent 循环）
- 多模态不可用（Key/网络受限）：以文本问答 + 图谱为主，说明图片链路已实现并可复现

---

## 种子数据

三类典型工业设备，覆盖摩托车发动机、螺杆空压机、数控机床：

| 设备类型 | 手册片段 | SOP 步骤 | 检修案例 | 设备台账 | 报修记录 |
|---|---|---|---|---|---|
| 摩托车发动机（通用四冲程） | 20 | 7 | 7 | 3 | 7 |
| 螺杆空压机（LS25-132） | 9 | 7 | 3 | 2 | 2 |
| 数控机床（CK6140） | 10 | 8 | 3 | 2 | 3 |
| **合计** | **39** | **22** | **13** | **7** | **12** |

知识图谱：**70+ 实体**（device / part / fault / cause / measure）、**66+ 关系边**（包含 / 发生 / 源于 / 采取）。另预置 **5 条反馈修正知识**，覆盖三类设备，可现场演示修正知识注入效果。

---

## 目录结构

```
backend/
  app/
    main.py                  FastAPI 入口（CORS、Prometheus 中间件、路由注册）
    config.py                全局配置 + 启动强校验（JWT_SECRET、枚举、CORS）
    db.py  models.py         ORM 模型与轻量迁移
    schemas.py               Pydantic 请求/响应（含 Diagnose* / ReasoningChain*）
    auth.py                  鉴权（pbkdf2 + JWT + 角色）
    llm/ embedding/ vl/      三类 provider 的可插拔实现
    rag/
      retriever.py           混合召回（pgvector + pg_trgm + RRF，SQLite 回退）
      pipeline.py            RAG 编排（检索 → 引用 → 多轮 → 反馈增强 → 生成）
      multimodal.py          图片 → VL 描述 → 文本检索 → 诊断 + 安全拦截
      agent_diagnosis.py     ReAct 自主诊断（Thought/Action/Observation + 失败降级）
      graph_rag.py           图谱上下文、多跳推理链、故障树构建
      confidence.py          多维可解释评分
      feedback.py            人工修正召回与注入
      report_gen.py  alert_gen.py  sop_gen.py  sop_recommend.py
      kg_extract.py  kg_align.py  query_rewrite.py  device_context.py  security.py
    ingest.py                PDF/文本 → 切块 → 向量化 → 入库
    kg_store.py              图谱去重 upsert 与关系落库
    upload_guard.py          上传文件校验（类型/大小/路径穿越）
    audit_log.py  ratelimit.py  metrics.py
    routers/                 auth / chat / documents / sop / cases / kg / feedback
                             / devices / dashboard / alert / audit
    seed.py                  3 类设备种子数据 + 图谱 + 修正知识
  tests/                     pytest 套件（含 pgvector 契约测试）
  evaluation/                检索消融、Agent 评测、30 并发/SSE 压测
  requirements.txt           开发依赖
  requirements-server.txt    生产依赖（LoongArch 友好，不含原生扩展）
  Dockerfile
frontend/
  src/
    views/                   Dashboard / Chat / AgentDiagnosis / Devices / Alert
                             / Scan / SOP / Cases / Graph / Feedback / Documents / Audit
    components/  config/     公共组件与前端配置
    styles.css               亮/暗双主题变量、响应式断点、骨架屏
  nginx.conf  Dockerfile     静态托管 + /api 反代 + SSE 透传
deploy/
  deploy.sh                  银河麒麟 + LoongArch 一键部署
  00_smoke_test.sh           部署前依赖体检
  02_install_pgvector.sh     pgvector 编译安装
  03_migrate_pgvector.sql    pgvector 表结构与索引迁移
  04_backup_restore.sh       备份 / 恢复
  05_collect_loongarch_evidence.sh  实机稳定性证据采集
  generate_sbom.py           CycloneDX SBOM 生成
  nginx/  systemd/           Nginx 与 systemd 模板
docs/                        路线图、需求证据矩阵、演示脚本、答辩追问
.github/workflows/ci.yml     双作业 CI
docker-compose.yml           前后端一键编排
docker-compose.pgvector.yml  追加 PostgreSQL + pgvector
samples/                     图片问答示例素材
```

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/national-special-roadmap.md](docs/national-special-roadmap.md) | 三阶段路线、退出条件与量化目标 |
| [docs/requirements-evidence-matrix.md](docs/requirements-evidence-matrix.md) | 赛题要求 → 代码入口 → 自动化/演示证据 |
| [docs/demo-4min-script.md](docs/demo-4min-script.md) | 4 分钟主演示脚本与硬检查项 |
| [docs/defense-qa.md](docs/defense-qa.md) | 答辩追问库（技术价值、边界、国产化） |

---

## 已知边界与口径

- **SQLite 是演示回退**。生产检索结论以 PostgreSQL + pgvector 实测为准；pgvector 装不上时只能完成功能演示，不得据此宣称生产检索性能。
- **未实测的数字不写成结论**。评测脚本产出的报告落在 `evidence/`，答辩引用以实机/CI 记录为准。
- **0.85^n 是可解释评分**，完成标注校准前不称其为统计置信度。
- **LoongArch 实机结论待采集**：`deploy/05_collect_loongarch_evidence.sh` 默认拒绝在非龙芯架构生成正式证据。
- **本地无 PostgreSQL 时**，依赖 `TEST_POSTGRES_URL` 的集成用例会跳过，合并前以 CI 成功记录为准。
