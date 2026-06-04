"""初始化数据：建表 + 默认用户 + 种子检修知识（含向量）。

运行：python -m app.seed
默认账号：
  worker / worker123   （一线人员）
  auditor / auditor123 （审核员）
  admin / admin123     （管理员）
"""
from sqlalchemy import select

from .auth import hash_password
from .db import Base, SessionLocal, engine
from .embedding import get_embedder
from .models import DocChunk, Document, User

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

        print("初始化完成。账号：worker/worker123, auditor/auditor123, admin/admin123")
    finally:
        db.close()


if __name__ == "__main__":
    run()
