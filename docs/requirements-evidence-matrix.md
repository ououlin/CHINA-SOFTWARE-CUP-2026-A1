# 赛题需求与证据矩阵

| 能力 | 代码入口 | 自动化证据 | 演示证据 | 当前判定 |
|---|---|---|---|---|
| 文本知识检索与引用 | `app/rag/pipeline.py`、`app/rag/retriever.py` | `tests/test_chat.py`、`evaluation/evaluate_retrieval.py` | 问答页引用卡 | 已实现；生产指标待采集 |
| 图片故障问答 | `app/rag/multimodal.py` | `tests/test_chat.py` | 故障图上传与拒绝样例 | 已实现，缺视觉标注集 |
| 标准化作业指引 | `app/routers/sop.py` | `tests/test_sop.py` | SOP 必检项拦截 | 已实现 |
| 案例沉淀与审核 | `app/routers/cases.py` | 后续补审核链路测试 | 案例提交、审核、入库 | 已实现，证据需补强 |
| 知识图谱与推理链 | `app/rag/graph_rag.py` | `tests/test_kg.py`、`tests/test_agent.py` | 图谱、Sankey、FTA | 已实现；评分尚未校准 |
| 回答标注修正闭环 | `app/routers/feedback.py` | `tests/test_feedback.py` | 修正发布后再次命中 | 已实现 |
| 一机一档 | `app/routers/devices.py` | `tests/test_devices.py` | 扫码调档、维修时间线 | 已实现 |
| 自主诊断 Agent | `app/rag/agent_diagnosis.py` | `tests/test_agent.py`、`evaluation/evaluate_agent.py` | 工具调用时间线 | 结构化协议已实现；真实模型指标待采集 |
| 权限、安全与审计 | `app/auth.py`、`app/rag/security.py`、`app/routers/audit.py` | `tests/test_auth.py`、`tests/test_security.py` | 越权拒绝、风险提示和审计记录 | 已实现 |
| PostgreSQL + pgvector | `app/rag/retriever.py`、`deploy/03_migrate_pgvector.sql` | `tests/test_pgvector.py`、`evaluation/evaluate_ablation.py` | 查询计划与消融报告 | SQL Top-K/RRF 已实现；真实库指标待采集 |
| LoongArch + 麒麟部署 | `deploy/` | `00_smoke_test.sh`、`05_collect_loongarch_evidence.sh` | 实机日志、截图、录像 | 采集链已实现，尚缺实机证据 |
| 性能与稳定性 | `app/metrics.py`、`evaluation/load_test.py` | SSE 故障注入测试、30 并发报告 | 指标报告 | 工具已实现，生产报告待采集 |
| 离线与可复现交付 | `requirements-server.txt`、`deploy/generate_sbom.py` | CycloneDX SBOM、SHA256、备份恢复记录 | 离线安装与恢复录像 | 工具已实现，目标机待验 |

## 证据包目录约定

后续实验结果统一写入 `evidence/`：

- `evidence/evaluation/`：检索、引用、Agent 和消融实验结果。
- `evidence/performance/`：负载测试原始数据与汇总。
- `evidence/loongarch/`：系统信息、安装日志、服务状态和稳定性记录。
- `evidence/security/`：攻击用例与审计结果。
- `evidence/demo/`：主备演示脚本和录屏清单。
