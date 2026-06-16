# 基于多模态大模型技术的设备检修知识检索与作业系统

> 第十五届中国软件杯 A 组赛题 · 龙芯中科出题

面向工业 / 制造业设备检修场景的 B/S 系统，融合**多模态知识检索、标准化作业指引、知识沉淀与知识图谱、大模型输出标注修正**四大能力，把分散的检修手册与一线经验沉淀为「可检索、可执行、可演进」的智能知识体系。

- 大模型走**云端 API**（DeepSeek 对话 + Qwen-VL 多模态），服务器无需 GPU
- 向量检索用 **pgvector**（开发期 SQLite，生产 PostgreSQL），不引入重型中间件
- 前端编译为静态文件、后端纯 Python 依赖——整体规避在 **LoongArch + 银河麒麟**上的架构兼容风险

---

## 四大核心功能

### ① 多模态知识检索（M1 + M2）

- **文本问答**：query → 向量检索 Top-K → 引用溯源 → DeepSeek **流式**生成，答案句末带 `[序号]` 出处，UI 展示引用卡片与相似度
- **故障图片问答**：上传图片 → **Qwen-VL** 看图输出结构化故障描述 → 跨模态对齐文本检索 → 结合手册片段诊断
- **设备型号过滤**：语义检索叠加精确过滤，「语义 + 结构化」混合检索

### ② 标准化作业指引（M3）

- **流程模板**：设备类型 × 检修等级 → 有序步骤，每步挂操作要点 / 风险提示 / 所需工具
- **合规校验拦截**：必检项未勾选时，前端「下一步」禁用 + 后端 `422` 二次拦截，双重保险
- **个性化推送**：按设备类型 + 检修等级筛选；可由大模型依检索手册片段**生成流程草稿**，审核员校核后发布
- 作业完成归档，「作业记录」可查审计闭环

### ③ 知识沉淀与知识图谱（M4）

- 一线人员提交检修案例 → **待审核**队列；审核员采纳后即触发：
  - 切块向量化入库（`source_type=case`），案例**立即可被 RAG 检索并作为引用**
  - 大模型**抽取实体与关系**（设备 / 部件 / 故障 / 原因 / 措施）写入知识图谱表
- **知识图谱可视化**：ECharts 力导向图，`(name, etype)` 去重让节点跨案例共享；点击节点溯源关联案例

### ④ 大模型输出标注与修正（M5）

- 每条回答可**点赞 / 点踩 + 文字纠正**
- **反馈增强闭环**：纠正沉淀为「修正知识」，再遇相似问题时**作为权威依据优先注入**上下文；前端展示「⚡ 本回答已采纳 N 条人工修正」横幅
- **治理**：「标注修正」页统计满意度与修正知识，审核员可下架 / 恢复不当纠正（下架即移出闭环）

---

## 技术栈

| 层 | 技术 | LoongArch / 麒麟可行性 |
|---|---|---|
| 前端 | Vue3 + Vite + Element Plus + ECharts | ✅ 开发机预编译静态文件，服务器仅托管 |
| Web 服务 | Nginx（反代 + 静态托管 + SSE 透传） | ✅ 麒麟官方源自带 |
| 后端 | Python + FastAPI + Uvicorn（纯净版） | ✅ 纯 Python，无 C 扩展依赖 |
| 数据库 | 开发期 SQLite，生产 PostgreSQL + pgvector | ✅ pgvector 纯 C 扩展可编译 |
| 大模型 | DeepSeek（对话）/ Qwen-VL（多模态） | ✅ 仅需 HTTPS 出网 |
| Embedding | 本地 fastembed（开发）/ DashScope 云端（生产） | ✅ 可插拔 provider，生产不装 onnxruntime |
| 知识图谱 | PostgreSQL 关系表 + ECharts（避开 Neo4j） | ✅ |
| 鉴权 | JWT + pbkdf2（标准库） | ✅ 免原生依赖 |

---

## 角色与演示账号

| 账号 | 密码 | 角色 | 权限 |
|---|---|---|---|
| `worker` | `worker123` | 一线人员 | 问答、执行作业、提交案例、反馈纠正 |
| `auditor` | `auditor123` | 审核员 | + 审核案例 / 发布 SOP / 治理修正 / 导入手册 |
| `admin` | `admin123` | 管理员 | 全部权限 |

---

## 本地开发

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 配置密钥（图片问答另需 DASHSCOPE_API_KEY）
copy .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 初始化数据库与种子数据（首次会下载本地嵌入模型，需联网一次）
.\.venv\Scripts\python.exe -m app.seed

# 启动
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Swagger 文档：http://127.0.0.1:8000/docs

### 前端

```powershell
cd frontend
npm install
npm run dev
```

访问 http://127.0.0.1:5173（开发期 `/api` 代理到 8000）。

> **图片问答演示**：聊天页点「故障图片」上传 `samples/fault_panel_overheat.png`。  
> **DashScope 国际站**：需在 `.env` 设 `DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/...`，否则 401。

---

## 生产部署（LoongArch + 银河麒麟）

### 部署架构

```
浏览器 ──HTTP/SSE──▶ Nginx ──┬── 静态文件（frontend/dist，开发机预编译）
                              └── /api 反代 ──▶ Gunicorn+Uvicorn(FastAPI) ──▶ PostgreSQL
                                                        │
                                                        └──HTTPS──▶ 云端大模型
                                                                   (DeepSeek / DashScope)
```

### LoongArch 风险规避

龙芯上最大的坑是「带原生扩展的 Python 包无预编译 wheel、需现场编译甚至无法编译」，本方案逐一规避：

| 风险点 | 规避方案 |
|---|---|
| fastembed / onnxruntime（ONNX 在龙芯兼容性差） | 生产用 `EMBEDDING_PROVIDER=dashscope` 云端嵌入，不装 |
| psycopg2（需 libpq + 编译） | 改用纯 Python 驱动 **pg8000**，零编译 |
| uvicorn[standard]（uvloop / httptools C 扩展） | 用纯净版 uvicorn，标准库 asyncio，性能足够 |
| PyMuPDF（C 扩展） | 延迟导入，装不上不影响启动，仅 PDF 上传不可用 |
| pgvector（需源码编译） | 默认 JSON 存向量 + 应用内余弦，可选装 |
| pydantic-core（Rust 编译） | 若无 wheel 则装 rust/cargo 让 pip 编译（唯一可能需要的现场编译） |

### 部署步骤

**第一步：在开发机（Windows）构建前端**

```powershell
cd frontend
npm run build        # 生成 frontend/dist，压缩后上传到服务器
```

**第二步：在服务器（麒麟）上准备代码**

```bash
# 若未装 git，先装
sudo dnf install -y git        # 或 sudo yum install -y git

# clone 代码
sudo git clone https://github.com/ououlin/CHINA-SOFTWARE-CUP-2026-A1.git /opt/device-repair
cd /opt/device-repair
```

**第三步：填写密钥**

```bash
# 生成 .env 模板（首次运行 deploy.sh 也会自动生成并提示）
cp deploy/.env.production.example backend/.env
# 编辑填入密钥（无法打字可用 cat tee 方式写入，见下方提示）
```

需填写的关键字段：

| 字段 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek 对话 API Key |
| `DASHSCOPE_API_KEY` | 阿里云百炼 Key（Qwen-VL + Embedding） |
| `DATABASE_URL` | 演示推荐 `sqlite:////opt/device-repair/backend/app.db` |
| `JWT_SECRET` | 任意随机字符串 |

**第四步：一键部署**

```bash
sudo bash deploy/deploy.sh
```

脚本自动完成：系统依赖安装 → 数据库初始化 → 后端 venv/种子/systemd → Nginx 配置启动。

若运行时提示 `frontend/dist` 不存在，先上传 dist 再重跑一次即可。

完成后访问 `http://<服务器IP>/`。

> **可选**：`sudo bash deploy/02_install_pgvector.sh` 编译安装 pgvector（不装则用内存余弦，演示量够用）。  
> **诊断**：`bash deploy/00_smoke_test.sh` 可在部署前评估 Python 依赖兼容性。

### 排雷手册

**pydantic-core 编译失败**

```bash
sudo dnf install -y rust cargo
# 重新跑 04，或手动：backend/.venv/bin/pip install pydantic==2.6.4
```

**Nginx 502（SELinux 拦截反代）**

```bash
sudo setsebool -P httpd_can_network_connect 1
```

**SSE 不流式、整段才出** → 确认 Nginx 配置有 `proxy_buffering off`（本配置已设置）。

**PyMuPDF / onnxruntime 装不上** → 不影响启动，忽略即可。

**应急：先用 SQLite 跑通** → 把 `backend/.env` 改 `DATABASE_URL=sqlite:///./app.db`，重跑 `04`。

### 验证

```bash
curl http://127.0.0.1:8000/api/health     # {"status":"ok","stage":"M5"}
systemctl status device-repair-backend nginx
journalctl -u device-repair-backend -n 50
```

### 运维

```bash
# 重启后端
sudo systemctl restart device-repair-backend

# 更新代码
cd /opt/device-repair && sudo git pull
sudo bash deploy/04_deploy_backend.sh    # 重装依赖 + 迁移 + 重启

# 前端更新：开发机重新 npm run build，拷 dist，重跑 05
```

---

## 进度

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 | 骨架 + JWT 登录 + 最小 RAG 链路 | ✅ 已端到端验证 |
| M2 | 多模态检索（Qwen-VL）+ 型号过滤 + PDF 手册导入 | ✅ 已端到端验证 |
| M3 | 标准化作业指引（模板 / 步骤 / 合规 / 推送） | ✅ 已端到端验证 |
| M4 | 知识沉淀（上传-审核-入库-抽图谱）+ 知识图谱可视化 | ✅ 已端到端验证 |
| M5 | 大模型输出标注与修正（反馈增强闭环） | ✅ 已端到端验证 |
| M6 | LoongArch + 麒麟生产部署 | 🟡 进行中 |
| M7 | 文档 + PPT + 演示视频 | ⏳ 待完成 |

> **四大核心功能已全部实现并验证。**

---

## 目录结构

```
backend/
  app/
    config.py               配置（可插拔 provider）
    db.py  models.py        数据库与 ORM
    schemas.py              Pydantic 请求响应模型
    auth.py                 鉴权（pbkdf2 + JWT + 角色）
    llm/                    LLM provider（DeepSeek）
    embedding/              Embedding provider（local / dashscope）
    vl/                     视觉 provider（Qwen-VL）
    rag/
      retriever.py          向量检索 + 型号过滤
      pipeline.py           RAG 编排（检索 → 引用 → 反馈增强 → LLM）
      multimodal.py         图片 → VL 描述 → 文本检索 → 诊断
      sop_gen.py            依手册生成 SOP 草稿
      kg_extract.py         案例抽取知识图谱实体/关系
      feedback.py           反馈增强：召回相似问题的人工修正
    ingest.py               PDF / 文本 → 切块 → 向量化 → 入库
    kg_store.py             知识图谱去重 upsert + 关系落库
    routers/                auth / chat / documents / sop / cases / kg / feedback
    seed.py                 初始化数据（账号 + 种子手册/SOP/案例/图谱）
frontend/
  src/
    views/                  Login / Chat / Documents / SOP / Cases / Graph / Feedback
    api.js  store.js  router.js
deploy/
  deploy.sh                 一键部署（系统依赖→数据库→后端→前端+Nginx）
  00_smoke_test.sh          依赖冒烟测试（部署前诊断用）
  02_install_pgvector.sh    pgvector 编译安装（可选）
  .env.production.example   密钥模板
samples/
  fault_panel_overheat.png  图片问答演示样例
项目技术方案与整体规划.md    设计与选型详述（含 LoongArch 可行性分析）
```
