# 部署指南（LoongArch + 银河麒麟高级服务器版）

本目录提供在 **龙芯 LoongArch + 银河麒麟高级服务器版 V10/V11** 上部署本系统的脚本与配置。

## 0. 部署形态

服务器仅 3~4 个进程，全部在麒麟/LoongArch 上有成熟支持：

```
浏览器  ──HTTP/SSE──▶  Nginx ──┬─ 静态文件(前端 dist，开发机预构建)
                                └─ /api 反代 ─▶ Gunicorn+Uvicorn(FastAPI) ─▶ PostgreSQL
                                                          │
                                                          └──HTTPS──▶ 云端大模型(DeepSeek / DashScope Qwen-VL、Embedding)
```

## 1. 设计要点：把 LoongArch 编译风险降到最低

部署到龙芯最大的坑是「带原生扩展的 Python 包在 LoongArch 上无预编译 wheel、需现场编译甚至无法编译」。本方案逐一规避：

| 风险点 | 默认规避方案 | 说明 |
|---|---|---|
| **Embedding**：fastembed→onnxruntime（ONNX 在龙芯兼容性差） | `EMBEDDING_PROVIDER=dashscope` 用**云端嵌入** | 服务器不装 fastembed/onnxruntime |
| **PostgreSQL 驱动**：psycopg2 需 libpq + 编译 | **pg8000**（纯 Python 驱动，零编译） | `postgresql+pg8000://...` |
| **ASGI 加速**：uvicorn[standard] 的 uvloop/httptools（C 扩展） | 用**纯净版 uvicorn**（标准库 asyncio） | 性能足够，零编译 |
| **PDF 解析**：PyMuPDF（C 扩展，龙芯可能装不上） | 代码**延迟导入**，不装不影响启动 | 仅"上传 PDF 手册"不可用，可用纯文本案例替代 |
| **向量索引**：pgvector（需源码编译） | **可选**，默认 JSON 存向量 + 应用内余弦 | 演示数据量下足够；需要再装（脚本 02） |
| **大模型推理**：本地算力/算子 | 全走**云端 API** | 服务器无需 GPU |
| **pydantic-core**（Rust 编译） | 若无 wheel 则装 Rust 让 pip 编译 | 见下方排雷；这是唯一可能需现场编译的核心件 |

> 结论：除 PostgreSQL、Nginx（麒麟源自带，已为 LoongArch 预编译）外，Python 侧尽量纯 Python，把"必须现场编译"的东西压缩到几乎为零。

## 2. 前置准备

1. **一台麒麟 V10/V11（LoongArch）虚机**，有 root（或 sudo）与外网访问（调云端 API）。
2. **云端 Key**：DeepSeek Key、DashScope（百炼）Key。
3. **把代码放到服务器** `/opt/device-repair`（推荐）：
   ```bash
   sudo git clone https://github.com/ououlin/CHINA-SOFTWARE-CUP-2026-A1.git /opt/device-repair
   ```
4. **前端构建产物**（在开发机/Windows 上构建，避免龙芯上跑 Node 工具链）：
   ```powershell
   cd frontend ; npm install ; npm run build      # 生成 frontend/dist
   ```
   再拷到服务器：`scp -r frontend/dist root@<server>:/opt/device-repair/frontend/`

## 3. 部署步骤（按序执行）

```bash
cd /opt/device-repair

# ① 装系统依赖（python/pg/nginx/编译工具）
sudo bash deploy/01_install_system_deps.sh

# ② 依赖冒烟（M0 排雷）：报告哪些 Python 依赖可装、pgvector 是否可用
bash deploy/00_smoke_test.sh

# ③ 初始化数据库（设置库密码）
sudo DB_PASSWORD='强密码' bash deploy/03_setup_database.sh

# ④ （可选）编译 pgvector —— 不需要可跳过
# sudo bash deploy/02_install_pgvector.sh

# ⑤ 填密钥：复制模板并编辑（首次跑 04 会自动复制并提示）
cp deploy/.env.production.example backend/.env
vi backend/.env       # 填 DEEPSEEK_API_KEY / DASHSCOPE_API_KEY / DATABASE_URL / JWT_SECRET

# ⑥ 部署后端（venv+依赖+种子+systemd 服务）
sudo bash deploy/04_deploy_backend.sh

# ⑦ 部署前端 + Nginx（需先放好 frontend/dist）
sudo bash deploy/05_deploy_frontend.sh
```

完成后浏览器访问 `http://<服务器IP>/`，演示账号 `worker/worker123`、`auditor/auditor123`、`admin/admin123`。

## 4. LoongArch 排雷手册

**`pip install` 报 pydantic-core 编译失败 / 找不到 wheel**
最可能需要现场编译的核心件。装 Rust 后让 pip 自行编译：
```bash
sudo dnf install -y rust cargo
# 重新执行 04，或手动： backend/.venv/bin/pip install pydantic==2.6.4
```
若仍失败，可考虑换用麒麟源里已为 loong64 打包的 python3-pydantic，或退回 pydantic v1 兼容分支（需小改 schemas，作为最后手段）。

**onnxruntime / fastembed 装不上** → 不用管。服务器走 `EMBEDDING_PROVIDER=dashscope`，本就不装它。

**psycopg2 装不上** → 不用管。已用纯 Python 的 `pg8000`，`DATABASE_URL=postgresql+pg8000://...`。

**PyMuPDF 装不上** → 不影响启动。仅"上传 PDF 手册"不可用，改用「知识沉淀」里的纯文本案例录入即可。若需要，单独 `pip install PyMuPDF`。

**pgvector** → 默认不需要（JSON + 内存余弦）。要用就跑 `02_install_pgvector.sh` 并 `CREATE EXTENSION vector`。

**Nginx 502 / 无法访问后端**（SELinux）：
```bash
sudo setsebool -P httpd_can_network_connect 1   # 允许 nginx 反代到 127.0.0.1:8000
sudo systemctl status device-repair-backend     # 确认后端在跑
```

**前端能开、接口 404/跨域** → 确认 `/api/` 走的是 Nginx 同源反代（本配置已处理），不要直连 8000。

**SSE 不流式、整段才出** → 确认未被中间代理缓冲；本 Nginx 配置已 `proxy_buffering off`。

## 5. 验证

```bash
curl http://127.0.0.1:8000/api/health          # {"status":"ok","stage":"M5"}
systemctl status device-repair-backend nginx
journalctl -u device-repair-backend -n 50      # 后端日志
```
浏览器跑一遍：登录 → 智能检修问答（文本/图片）→ 作业指引 → 知识沉淀（提交+审核）→ 知识图谱 → 标注修正。

## 6. 运维

```bash
# 重启/查看后端
sudo systemctl restart device-repair-backend
journalctl -u device-repair-backend -f

# 更新代码后重新部署
cd /opt/device-repair && sudo git pull
sudo bash deploy/04_deploy_backend.sh           # 重装依赖+迁移+重启
# 前端：开发机重新 npm run build，拷 dist，过 05 即可
```

## 7. 应急：先用 SQLite 跑通

若 PostgreSQL 一时未就绪，可临时用 SQLite（纯文件、零依赖）先让系统跑起来：把 `backend/.env` 改成
`DATABASE_URL=sqlite:///./app.db`，重跑 `04` 即可。功能完全一致，仅并发写能力弱，适合演示与联调。

---

文件清单：`00_smoke_test.sh`(排雷) `01_install_system_deps.sh` `02_install_pgvector.sh`(可选)
`03_setup_database.sh` `04_deploy_backend.sh` `05_deploy_frontend.sh`；
配置：`.env.production.example` `gunicorn_conf.py` `systemd/` `nginx/`。
