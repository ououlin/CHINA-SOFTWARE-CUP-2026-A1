"""初始化数据：建表 + 默认用户 + 种子检修知识（含向量）。

运行：python -m app.seed
默认账号：
  worker / worker123   （一线人员）
  auditor / auditor123 （审核员）
  admin / admin123     （管理员）
"""
import datetime as dt

from sqlalchemy import select

from .auth import hash_password
from .db import Base, SessionLocal, engine
from .embedding import get_embedder
from .ingest import ingest_text
from .kg_store import persist_extraction
from .models import (
    DocChunk, Document, RepairCase, SOPStep, SOPTemplate, User,
)

# 种子检修知识：以摩托车发动机为例（赛题参考手册主题），便于演示。
SEED_DOC = {
    "title": "摩托车发动机维修手册（节选）",
    "source_type": "manual",
    "device_model": "通用四冲程",
    "device_type": "摩托车发动机",
}

SEED_CHUNKS = [
    (12, "发动机怠速不稳的常见原因：1) 化油器怠速油路堵塞或混合比失调；"
         "2) 火花塞积碳或间隙不当；3) 进气系统漏气；4) 气门间隙过大或过小。"
         "排查时应先检查火花塞与气门间隙，再清洗化油器怠速油路。"),
    (15, "火花塞检查与更换：正常火花塞电极呈浅棕色。若电极积碳发黑，"
         "说明混合气过浓或长期低速运转；若电极发白，说明混合气过稀或点火过早。"
         "标准电极间隙为 0.6~0.7mm，使用塞尺测量，必要时更换同型号火花塞。"),
    (23, "气门间隙调整：发动机冷态下，使活塞处于压缩上止点。"
         "进气门标准间隙 0.05mm，排气门标准间隙 0.08mm。"
         "用塞尺测量，松开锁紧螺母调整调整螺钉至规定间隙后锁紧。"
         "间隙过大会导致气门响、动力下降；过小会导致气门关闭不严、漏气。"),
    (31, "机油更换与润滑：建议每行驶 1000~1500 公里更换一次机油。"
         "更换时先热车使机油充分流动，停机后拧下放油螺塞放尽旧油，"
         "装回螺塞并加注规定标号的新机油至油标尺上下刻度之间。机油不足会加剧磨损。"),
    (38, "发动机过热处理：过热常因冷却不良、机油不足或点火时刻不当引起。"
         "风冷发动机应检查散热片是否被泥垢堵塞；检查机油量与品质；"
         "检查点火正时是否过迟。持续过热会导致拉缸、活塞环卡死等严重故障。"),
]

# 种子作业流程（SOP）：摩托车发动机二级维护，含合规必检项，开箱即演示。
# 每步：(序号, 标题, 操作要点, 风险提示, 所需工具, 是否必检 1/0, 合规确认项)
SEED_SOP = {
    "name": "摩托车发动机二级维护标准作业流程",
    "device_type": "摩托车发动机",
    "device_model": "通用四冲程",
    "repair_level": "二级维护",
    "summary": "适用于通用四冲程摩托车发动机的定期二级维护，涵盖火花塞、气门间隙、"
               "机油更换等关键项，并设置安全与质量合规必检点。",
    "steps": [
        (1, "作业前安全准备",
         "确认发动机已熄火且处于冷态；关闭油路开关、取下钥匙；佩戴手套与护目镜；备好灭火器材。",
         "热态作业易烫伤；未断油路可能漏油起火。", "手套, 护目镜, 灭火器", 1,
         "已确认发动机冷却、已关闭油路并佩戴防护用品"),
        (2, "外观与漏油检查",
         "检查发动机外壳、油封、油管接头有无渗漏与裂纹，记录异常部位。",
         "", "手电筒, 抹布", 0, ""),
        (3, "火花塞检查与间隙调整",
         "拆下火花塞，观察电极颜色判断燃烧状况；用塞尺测量电极间隙，"
         "调整至 0.6~0.7mm，必要时更换同型号火花塞。",
         "电极间隙不当会导致点火不良、动力下降。", "火花塞套筒, 塞尺", 1,
         "火花塞电极间隙已校至 0.6~0.7mm"),
        (4, "气门间隙检查与调整",
         "冷态下使活塞处于压缩上止点，用塞尺测量并调整：进气门 0.05mm、排气门 0.08mm，"
         "松开锁紧螺母调整后重新锁紧。",
         "间隙过小会漏气甚至拉缸，过大会气门响、动力下降。", "塞尺, 套筒扳手, 螺丝刀", 1,
         "进/排气门间隙已校至 0.05/0.08mm"),
        (5, "更换机油",
         "热车后停机，拧下放油螺塞放尽旧油，装回螺塞并加注规定标号机油至油标尺上下刻度之间。",
         "刚停机机油温度高，注意防烫。", "放油扳手, 油盆, 漏斗, 新机油", 0, ""),
        (6, "怠速与点火正时复检",
         "启动发动机，检查怠速是否平稳、有无异响；核对点火正时，必要时微调化油器怠速螺钉。",
         "怠速过高或点火过迟会导致发动机过热。", "转速表", 1,
         "怠速平稳无异响、点火正时正常"),
        (7, "作业后清理与记录",
         "清理工位与工具，废油按规定回收处置；填写维护记录与下次保养里程。",
         "", "抹布, 废油回收桶", 0, ""),
    ],
}


# 种子检修案例（M4 知识沉淀）：2 条已采纳（含手工知识图谱，离线可种，
# 共享「摩托车发动机」设备节点形成跨案例关联）+ 1 条待审核（供审核演示）。
SEED_CASES = [
    {
        "title": "怠速不稳故障检修案例",
        "device_type": "摩托车发动机",
        "device_model": "通用四冲程",
        "content": "故障现象：发动机怠速不稳、易熄火，补油后可恢复。"
                   "排查过程：拆检火花塞发现电极积碳发黑、间隙偏大；"
                   "拆检化油器发现怠速油路有油泥堵塞。"
                   "处理措施：清洗化油器怠速油路，更换同型号火花塞并将电极间隙校至 0.7mm。"
                   "复机后怠速平稳，故障排除。",
        "kg": {
            "entities": [
                {"name": "摩托车发动机", "etype": "device"},
                {"name": "化油器", "etype": "part"},
                {"name": "火花塞", "etype": "part"},
                {"name": "怠速不稳", "etype": "fault"},
                {"name": "化油器怠速油路堵塞", "etype": "cause"},
                {"name": "火花塞积碳", "etype": "cause"},
                {"name": "清洗化油器怠速油路", "etype": "measure"},
                {"name": "更换火花塞", "etype": "measure"},
            ],
            "relations": [
                {"source": "摩托车发动机", "rel": "包含", "target": "化油器"},
                {"source": "摩托车发动机", "rel": "包含", "target": "火花塞"},
                {"source": "摩托车发动机", "rel": "发生", "target": "怠速不稳"},
                {"source": "怠速不稳", "rel": "源于", "target": "化油器怠速油路堵塞"},
                {"source": "怠速不稳", "rel": "源于", "target": "火花塞积碳"},
                {"source": "怠速不稳", "rel": "采取", "target": "清洗化油器怠速油路"},
                {"source": "怠速不稳", "rel": "采取", "target": "更换火花塞"},
            ],
        },
    },
    {
        "title": "发动机过热故障检修案例",
        "device_type": "摩托车发动机",
        "device_model": "通用四冲程",
        "content": "故障现象：连续骑行后发动机过热、动力明显下降。"
                   "排查过程：发现风冷散热片附着大量泥垢、严重影响散热；"
                   "检查机油尺，机油液位低于下限。"
                   "处理措施：清理散热片泥垢，补充规定标号机油至油标尺上下刻度之间。"
                   "复机后温度恢复正常、动力回升。",
        "kg": {
            "entities": [
                {"name": "摩托车发动机", "etype": "device"},
                {"name": "散热片", "etype": "part"},
                {"name": "发动机过热", "etype": "fault"},
                {"name": "散热片堵塞", "etype": "cause"},
                {"name": "机油不足", "etype": "cause"},
                {"name": "清理散热片", "etype": "measure"},
                {"name": "补充机油", "etype": "measure"},
            ],
            "relations": [
                {"source": "摩托车发动机", "rel": "包含", "target": "散热片"},
                {"source": "摩托车发动机", "rel": "发生", "target": "发动机过热"},
                {"source": "发动机过热", "rel": "源于", "target": "散热片堵塞"},
                {"source": "发动机过热", "rel": "源于", "target": "机油不足"},
                {"source": "发动机过热", "rel": "采取", "target": "清理散热片"},
                {"source": "发动机过热", "rel": "采取", "target": "补充机油"},
            ],
        },
    },
]

SEED_PENDING_CASE = {
    "title": "气门异响故障检修案例",
    "device_type": "摩托车发动机",
    "device_model": "通用四冲程",
    "content": "故障现象：冷车启动后气门室有规律的'嗒嗒'金属敲击声，热车后略减轻、"
               "动力略有下降。初步判断为气门间隙过大。"
               "拟在冷态、压缩上止点下用塞尺复测并调整进/排气门间隙至标准值后观察。",
}


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # --- 默认用户 ---
        defaults = [
            ("worker", "worker123", "张工(一线)", "worker"),
            ("auditor", "auditor123", "李工(审核)", "auditor"),
            ("admin", "admin123", "管理员", "admin"),
        ]
        for username, pwd, name, role in defaults:
            exists = db.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()
            if not exists:
                db.add(User(username=username, display_name=name,
                            hashed_password=hash_password(pwd), role=role))
        db.commit()

        # --- 种子文档（仅首次）---
        exists_doc = db.execute(
            select(Document).where(Document.title == SEED_DOC["title"])
        ).scalar_one_or_none()
        if not exists_doc:
            doc = Document(**SEED_DOC, status="approved")
            db.add(doc)
            db.flush()
            embedder = get_embedder()
            texts = [c[1] for c in SEED_CHUNKS]
            print(f"正在生成 {len(texts)} 条种子向量 ...")
            vecs = embedder.embed(texts)
            for (page, content), vec in zip(SEED_CHUNKS, vecs):
                db.add(DocChunk(doc_id=doc.id, content=content,
                                page=page, embedding=vec))
            db.commit()
            print("种子检修知识已写入。")
        else:
            print("种子文档已存在，跳过。")

        # --- 种子 SOP 作业流程（仅首次）---
        exists_sop = db.execute(
            select(SOPTemplate).where(SOPTemplate.name == SEED_SOP["name"])
        ).scalar_one_or_none()
        if not exists_sop:
            tpl = SOPTemplate(
                name=SEED_SOP["name"], device_type=SEED_SOP["device_type"],
                device_model=SEED_SOP["device_model"],
                repair_level=SEED_SOP["repair_level"],
                summary=SEED_SOP["summary"], source="manual", status="approved",
            )
            db.add(tpl)
            db.flush()
            for order_no, title, instruction, risk, tools, req, cp in SEED_SOP["steps"]:
                db.add(SOPStep(
                    template_id=tpl.id, order_no=order_no, title=title,
                    instruction=instruction, risk=risk, tools=tools,
                    is_required=req, checkpoint=cp,
                ))
            db.commit()
            print(f"种子 SOP 作业流程已写入（{len(SEED_SOP['steps'])} 步）。")
        else:
            print("种子 SOP 已存在，跳过。")

        # --- 种子检修案例 + 知识图谱（仅首次）---
        exists_case = db.execute(select(RepairCase)).first()
        if not exists_case:
            worker = db.execute(
                select(User).where(User.username == "worker")
            ).scalar_one()
            auditor = db.execute(
                select(User).where(User.username == "auditor")
            ).scalar_one()
            print("正在写入种子检修案例并抽取知识图谱 ...")
            for sc in SEED_CASES:
                case = RepairCase(
                    title=sc["title"], device_type=sc["device_type"],
                    device_model=sc["device_model"], content=sc["content"],
                    author_id=worker.id, status="approved",
                    reviewed_by=auditor.id, reviewed_at=dt.datetime.utcnow(),
                    review_note="种子案例·示例采纳",
                )
                db.add(case)
                db.flush()
                doc = ingest_text(
                    db, title=case.title, content=case.content,
                    device_type=case.device_type, device_model=case.device_model,
                    source_type="case", status="approved",
                )
                case.doc_id = doc.id
                persist_extraction(db, case.id, sc["kg"])
                db.commit()
            # 1 条待审核案例
            db.add(RepairCase(
                title=SEED_PENDING_CASE["title"],
                device_type=SEED_PENDING_CASE["device_type"],
                device_model=SEED_PENDING_CASE["device_model"],
                content=SEED_PENDING_CASE["content"],
                author_id=worker.id, status="pending",
            ))
            db.commit()
            print(f"种子案例已写入（{len(SEED_CASES)} 条已采纳含图谱 + 1 条待审核）。")
        else:
            print("种子案例已存在，跳过。")

        print("初始化完成。账号：worker/worker123, auditor/auditor123, admin/admin123")
    finally:
        db.close()


if __name__ == "__main__":
    run()
