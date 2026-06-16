"""预测性维护建议生成（增强 G6）：把风险设备与故障统计交给 LLM，
生成针对性的预测性维护与预防建议（Markdown 文本）。
"""
from typing import List

from ..llm import get_llm

SYSTEM_PROMPT = (
    "你是工业设备预测性维护专家。请依据用户提供的【风险设备清单】与【高频故障统计】，"
    "给出专业、可执行的预测性维护建议，使用 Markdown 输出，包含：\n"
    "1. 总体风险研判（点明最需关注的设备与故障趋势）\n"
    "2. 重点设备维护建议（按设备给出针对性预防措施与建议检修周期）\n"
    "3. 高频故障预防要点（针对复发故障的根因防控）\n"
    "语言简洁专业，建议要具体可落地，只依据提供的数据，不要编造。"
)


def generate_maintenance_advice(risk_devices: List[dict], fault_stats: List[dict]) -> str:
    if risk_devices:
        dev_lines = []
        for d in risk_devices:
            dev_lines.append(
                f"- {d['name']}（编号 {d['code']}，型号 {d.get('device_model') or '—'}）："
                f"风险等级 {d['level']}，累计故障 {d['total']} 次，"
                f"近 30 天 {d['recent']} 次，严重/紧急 {d['urgent_serious']} 次，"
                f"未结 {d['open']} 项"
            )
        dev_text = "\n".join(dev_lines)
    else:
        dev_text = "（暂无明显风险设备）"

    if fault_stats:
        fault_text = "\n".join(
            f"- 型号 {f['name']}：累计故障 {f['value']} 次" for f in fault_stats)
    else:
        fault_text = "（暂无故障统计）"

    user = f"【风险设备清单】\n{dev_text}\n\n【高频故障统计（按型号）】\n{fault_text}"
    return get_llm().chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ])
