"""知识图谱抽取：从审核通过的检修案例正文中，用 LLM 抽取实体与关系三元组。

实体类型：device 设备 / part 部件 / fault 故障 / cause 原因 / measure 措施。
关系类型（建议）：包含 / 发生 / 源于 / 采取。
产出结构化 JSON，由路由层去重落库到 kg_entities / kg_relations。
"""
import json
import re
from typing import Dict, List

from ..llm import get_llm

ENTITY_TYPES = ("device", "part", "fault", "cause", "measure")
ETYPE_CN = {
    "device": "设备", "part": "部件", "fault": "故障",
    "cause": "原因", "measure": "措施",
}

KG_SYSTEM = (
    "你是工业设备检修领域的知识工程师。请从给定的检修案例中抽取知识图谱。"
    "实体分五类：device(设备)、part(部件)、fault(故障现象)、cause(故障原因)、measure(处理措施)。"
    "关系用简短动词短语，建议取值：包含(设备→部件)、发生(设备/部件→故障)、"
    "源于(故障→原因)、采取(故障→措施)。"
    "实体名称要规范、简洁（不超过20字），同一事物用统一称呼。"
    "只输出 JSON，不要任何解释或 Markdown 代码围栏。"
)

JSON_SPEC = (
    "请严格按以下 JSON 输出：\n"
    "{\n"
    '  "entities": [{"name": "实体名", "type": "device|part|fault|cause|measure"}],\n'
    '  "relations": [{"source": "源实体名", "rel": "关系", "target": "目标实体名"}]\n'
    "}\n"
    "relations 中出现的实体必须都在 entities 中。至少抽取 3 个实体与 2 条关系。"
)


def _extract_json(text: str) -> dict:
    if not text or not text.strip():
        raise ValueError("LLM 未返回内容")
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM 输出不含 JSON 对象")
    return json.loads(t[start:end + 1])


def extract_kg(
    content: str,
    title: str = "",
    device_type: str = "",
    device_model: str = "",
) -> Dict[str, List[dict]]:
    """调用 LLM 抽取实体/关系，返回清洗后的 {entities, relations}。"""
    user_content = (
        f"案例标题：{title or '（无）'}\n"
        f"设备类型：{device_type or '（未知）'}\n"
        f"设备型号：{device_model or '（通用）'}\n\n"
        f"【案例正文】\n{content}\n\n{JSON_SPEC}"
    )
    messages = [
        {"role": "system", "content": KG_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    data = _extract_json(get_llm().chat(messages, temperature=0.2))

    # 清洗实体：去空、限类型、按 (name,type) 去重
    entities: List[dict] = []
    seen = set()
    for e in data.get("entities", []):
        name = (e.get("name") or "").strip()[:128]
        etype = (e.get("type") or "").strip().lower()
        if not name or etype not in ENTITY_TYPES:
            continue
        key = (name, etype)
        if key in seen:
            continue
        seen.add(key)
        entities.append({"name": name, "etype": etype})

    name_set = {e["name"] for e in entities}
    # 清洗关系：两端实体须存在，去自环
    relations: List[dict] = []
    rel_seen = set()
    for r in data.get("relations", []):
        src = (r.get("source") or "").strip()[:128]
        dst = (r.get("target") or "").strip()[:128]
        rel = (r.get("rel") or "相关").strip()[:32]
        if not src or not dst or src == dst:
            continue
        if src not in name_set or dst not in name_set:
            continue
        key = (src, rel, dst)
        if key in rel_seen:
            continue
        rel_seen.add(key)
        relations.append({"source": src, "rel": rel, "target": dst})

    if not entities:
        raise ValueError("未能从案例中抽取到有效实体")
    return {"entities": entities, "relations": relations}
