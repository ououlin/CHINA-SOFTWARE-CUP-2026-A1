"""知识图谱实体对齐消歧（进阶 Entity Resolution）。

一线案例里同一事物常有多种写法（"1号泵" / "一号循环泵" / "#1给水泵"），
直接入库会让 ECharts 力导向图节点爆炸、杂乱。写入前先对齐到标准节点：
  ① 规则归一（全角半角 / 空格 / 符号 / 中文数字）匹配已有实体；
  ② 规则未命中的，用一次 LLM 语义对齐到同类已有实体（尽力而为，失败仅用规则）。
"""
import json
import re
import unicodedata
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from .llm import get_llm
from .models import KGEntity

_CN_NUM = {
    "零": "0", "〇": "0", "一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
}


def normalize_name(name: str) -> str:
    """规则归一：全角→半角、去空格、去 # 号、中文数字→阿拉伯数字、小写。"""
    s = unicodedata.normalize("NFKC", name or "").strip().lower()
    s = re.sub(r"\s+", "", s)
    s = s.replace("#", "")
    for cn, ar in _CN_NUM.items():
        s = s.replace(cn, ar)
    return s


def _existing_by_type(db: Session) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for e in db.execute(select(KGEntity)).scalars().all():
        out.setdefault(e.etype, []).append(e.name)
    return out


ALIGN_SYSTEM = (
    "你是工业设备知识图谱的实体对齐专家。给你一批【新实体】和【已有标准实体】，"
    "判断每个新实体是否与某个已有标准实体指同一事物（考虑别名、简称、编号写法差异，"
    "例如 '1号泵'='一号循环泵'='#1给水泵'）。是则对齐到该已有标准名，否则保持其本身。"
    '只输出 JSON：{"map": {"新实体名": "对齐到的标准名或其本身"}}，不要任何解释。'
)


def align_extraction(db: Session, entities: List[dict]) -> Dict[str, str]:
    """返回 {抽取原名: 标准名} 映射，供落库前归一节点。"""
    existing = _existing_by_type(db)
    mapping: Dict[str, str] = {}
    unresolved: List[dict] = []

    # ① 规则归一对齐
    for ent in entities:
        name, etype = ent["name"], ent["etype"]
        norm = normalize_name(name)
        hit = next((x for x in existing.get(etype, [])
                    if normalize_name(x) == norm), None)
        mapping[name] = hit if hit else None
        if not hit:
            unresolved.append(ent)

    # ② LLM 语义对齐（仅对规则未命中且库中已有同类实体时，尽力而为）
    if unresolved and any(existing.values()):
        try:
            cand = {et: existing.get(et, []) for et in {e["etype"] for e in unresolved}}
            user = (
                "【新实体】\n"
                + "\n".join(f"- {e['name']}（{e['etype']}）" for e in unresolved)
                + "\n\n【已有标准实体（按类型）】\n"
                + json.dumps(cand, ensure_ascii=False)
            )
            out = get_llm().chat([
                {"role": "system", "content": ALIGN_SYSTEM},
                {"role": "user", "content": user},
            ], temperature=0)
            m = json.loads(out[out.find("{"):out.rfind("}") + 1]).get("map", {})
            for e in unresolved:
                std = (m.get(e["name"]) or "").strip()
                mapping[e["name"]] = std or e["name"]
        except Exception:
            for e in unresolved:
                mapping[e["name"]] = e["name"]
    else:
        for e in unresolved:
            mapping[e["name"]] = e["name"]

    # 规则命中的填回标准名
    for ent in entities:
        if mapping.get(ent["name"]) is None:
            mapping[ent["name"]] = ent["name"]
    return mapping
