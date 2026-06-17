"""检修报告生成（增强 G5）：把设备台账 + 报修/维修时间线交给 LLM，
汇总成一份规范的《设备检修报告》（Markdown），供前端展示与导出。
"""
from typing import List

from ..llm import get_llm

SYSTEM_PROMPT = (
    "你是工业设备检修报告撰写助手。请依据用户提供的【设备台账】与【报修/维修记录】，"
    "撰写一份规范、专业、可直接归档的《设备检修报告》，使用 Markdown 输出。"
    "报告须包含以下小节：\n"
    "1. 设备概况（基本信息归纳）\n"
    "2. 检修记录汇总（按时间梳理已发生的故障与处理）\n"
    "3. 故障规律分析（识别高频/复发故障及可能根因）\n"
    "4. 维护建议（针对性的预防与保养建议）\n"
    "5. 结论\n"
    "语言简洁专业，只依据提供的事实，不要编造数据；若记录为空，也要给出合理的初始保养建议。"
)


def generate_device_report(device: dict, records: List[dict]) -> str:
    """同步调用 LLM 生成报告 Markdown 文本。"""
    info = (
        f"- 资产编号：{device.get('code', '')}\n"
        f"- 设备名称：{device.get('name', '')}\n"
        f"- 设备类型：{device.get('device_type', '') or '—'}\n"
        f"- 设备型号：{device.get('device_model', '') or '—'}\n"
        f"- 安装位置：{device.get('location', '') or '—'}\n"
        f"- 当前状态：{device.get('status', '') or '—'}\n"
        f"- 投运日期：{device.get('commissioned', '') or '—'}\n"
        f"- 累计报修：{len(records)} 次"
    )

    if records:
        rec_lines = []
        for i, r in enumerate(records, 1):
            rec_lines.append(
                f"{i}. [{r.get('created', '')}]（严重度：{r.get('severity', '')}，"
                f"状态：{r.get('status', '')}）{r.get('title', '')}\n"
                f"   现象：{r.get('fault', '') or '未记录'}\n"
                f"   处理：{r.get('handling', '') or '尚未处理'}"
            )
        rec_text = "\n".join(rec_lines)
    else:
        rec_text = "（暂无报修/维修记录）"

    user = f"【设备台账】\n{info}\n\n【报修/维修记录】\n{rec_text}"
    return get_llm().chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ])
