"""初始化数据：建表 + 默认用户 + 种子检修知识（含向量）。

运行：python -m app.seed
默认账号：
  worker / worker123   （一线人员）
  auditor / auditor123 （审核员）
  admin / admin123     （管理员）
"""
import datetime as dt
from datetime import timezone

from sqlalchemy import select

from .auth import hash_password
from .db import Base, SessionLocal, engine
from .embedding import get_embedder
from .ingest import ingest_text
from .kg_store import persist_extraction
from .models import (
    DocChunk, Document, RepairCase, SOPStep, SOPTemplate, User,
    Device, MaintenanceRecord, QALog, LLMFeedback,
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

# 摩托车发动机额外知识片段（补充手册覆盖面，让检索更丰富）
SEED_EXTRA_MOTO_CHUNKS = [
    (45, "离合器打滑故障排查：离合器打滑表现为加速时发动机转速升高但车速不变。"
         "常见原因：摩擦片磨损过薄、离合器弹簧弹力减弱、操纵拉索自由行程过小。"
         "排查时先检查拉索自由行程（标准 2~3mm），再拆检摩擦片厚度（极限 3.0mm），"
         "磨损超标须成套更换摩擦片与弹簧。"),
    (52, "变速箱异响诊断：空挡时有异响、踩下离合器消失，多为输入轴轴承磨损；"
         "行驶中各挡均有异响，为主轴或副轴轴承损坏；仅某挡异响，为该挡齿轮磨损。"
         "拆检变速箱须在清洁环境中进行，注意各挡齿轮啮合面与轴承游隙。"),
    (58, "启动困难故障排查：冷车启动困难先检查火花塞点火与化油器阻风门；"
         "热车启动困难多为点火线圈过热失效或油路气阻。"
         "电启动无力则检查蓄电池电压（应≥12.4V）、启动电机碳刷长度与单向离合器。"),
]

# === 螺杆空压机维修手册（节选）—— 第二设备类型，丰富知识库 ===
SEED_COMPRESSOR_DOC = {
    "title": "螺杆式空气压缩机维修手册（节选）",
    "source_type": "manual",
    "device_model": "LS25-132",
    "device_type": "螺杆空压机",
}

SEED_COMPRESSOR_CHUNKS = [
    (8, "螺杆空压机日常保养要点：每日检查油位、排气温度与压力是否正常；"
        "每周清洁空气滤芯；每月检查皮带张紧度与安全阀；每季度更换机油与油过滤器。"
        "排气温度超过 110°C 须立即停机排查冷却系统。"),
    (16, "排气压力低故障排查：排气压力低于设定值常见原因：1) 空气滤芯堵塞；"
        "2) 进气阀未全开或卡滞；3) 最小压力阀故障；4) 管路泄漏。"
        "先检查滤芯压差（超过 0.05MPa 须更换），再测进气阀动作，最后检查管路密封。"),
    (24, "空压机过热故障处理：排气温度过高常见原因：冷却器积灰、油量不足、"
        "温控阀故障、环境温度过高。风冷型先清洁冷却器翅片；水冷型检查冷却水流量与温度。"
        "油量低于油标下限须补充专用螺杆油，不同品牌机油严禁混用。"),
    (31, "空压机油路系统维护：螺杆油起润滑、密封、冷却三重作用。"
        "运行 2000 小时或半年须更换（先换油过滤器）。油乳化（乳白色）须立即换油并"
        "排查冷却器内漏。油路系统漏油会导致排气含油量超标、润滑不良。"),
    (38, "安全阀检查与校验：安全阀每年至少校验一次，设定压力为工作压力的 1.05~1.1 倍。"
        "手动测试须在空载下进行：拉动泄放拉环确认动作灵活，松开后能完全密封复位。"
        "安全阀泄漏或到压不启跳须立即更换，严禁超期使用。"),
]

# 空压机检修案例 + 知识图谱
SEED_COMPRESSOR_CASE = {
    "title": "螺杆空压机排气压力不足故障案例",
    "device_type": "螺杆空压机",
    "device_model": "LS25-132",
    "content": "故障现象：LS25-132 螺杆空压机排气压力仅 0.55MPa，低于设定 0.7MPa，"
               "用气端压力不足导致产线报警。"
               "排查过程：检查空气滤芯压差正常（0.02MPa）；手动测试进气阀发现阀芯动作迟缓；"
               "拆检进气阀发现阀芯密封面有油泥积碳。"
               "处理措施：用专用清洗剂清洗进气阀阀芯与密封面，更换阀芯密封圈。"
               "复机后排气压力恢复至 0.7MPa，产线正常运行。",
    "kg": {
        "entities": [
            {"name": "螺杆空压机", "etype": "device"},
            {"name": "进气阀", "etype": "part"},
            {"name": "空气滤芯", "etype": "part"},
            {"name": "排气压力不足", "etype": "fault"},
            {"name": "进气阀卡滞", "etype": "cause"},
            {"name": "阀芯油泥积碳", "etype": "cause"},
            {"name": "清洗进气阀", "etype": "measure"},
            {"name": "更换密封圈", "etype": "measure"},
        ],
        "relations": [
            {"source": "螺杆空压机", "rel": "包含", "target": "进气阀"},
            {"source": "螺杆空压机", "rel": "包含", "target": "空气滤芯"},
            {"source": "螺杆空压机", "rel": "发生", "target": "排气压力不足"},
            {"source": "排气压力不足", "rel": "源于", "target": "进气阀卡滞"},
            {"source": "进气阀卡滞", "rel": "源于", "target": "阀芯油泥积碳"},
            {"source": "排气压力不足", "rel": "采取", "target": "清洗进气阀"},
            {"source": "排气压力不足", "rel": "采取", "target": "更换密封圈"},
        ],
    },
}

# 空压机 SOP
SEED_COMPRESSOR_SOP = {
    "name": "螺杆空压机定期维护标准作业流程",
    "device_type": "螺杆空压机",
    "device_model": "LS25-132",
    "repair_level": "二级维护",
    "summary": "适用于 LS25-132 螺杆空压机的定期二级维护，涵盖滤芯、油路、"
               "冷却系统与安全阀等关键项，设置安全合规必检点。",
    "steps": [
        (1, "作业前安全准备",
         "确认空压机已停机并断电、挂警示牌；排放储气罐残余压缩空气至 0MPa；"
         "等待机头冷却至室温。",
         "带压作业易导致部件飞出伤人；高温机油溅射烫伤。", "绝缘手套, 护目镜, 警示牌", 1,
         "已断电挂牌、已泄压至 0MPa、机头已冷却"),
        (2, "空气滤芯检查与更换",
         "拆下空气滤芯，检查堵塞与破损情况；压差超过 0.05MPa 或使用超过 2000 小时须更换。",
         "滤芯破损会导致灰尘进入主机、加速转子磨损。", "扳手套件, 新滤芯", 0, ""),
        (3, "机油与油过滤器更换",
         "排放旧油，检查油色（乳白色为乳化须排查冷却器内漏）；更换油过滤器；"
         "加注专用螺杆油至油标上下限之间。",
         "不同品牌机油严禁混用；旧油须按规定回收。", "放油扳手, 油盆, 新机油, 油过滤器", 1,
         "机油无乳化、油量达标、油过滤器已更换"),
        (4, "冷却系统清洁",
         "风冷型：用压缩空气反吹冷却器翅片积灰；水冷型：检查冷却水流量与水垢情况。",
         "冷却不良会导致排气温度过高、自动停机。", "压缩空气源, 清洁刷", 0, ""),
        (5, "进气阀检查与清洗",
         "拆检进气阀阀芯与密封面，清除油泥积碳；检查弹簧弹力，密封圈老化须更换。",
         "进气阀卡滞会导致排气压力不足或空载电流过大。", "专用清洗剂, 密封圈, 扳手", 1,
         "进气阀阀芯动作灵活、密封面无积碳"),
        (6, "安全阀手动测试",
         "空载下拉动安全阀泄放拉环，确认动作灵活、松开后完全密封复位。",
         "安全阀失效可能导致储气罐超压爆炸。", "", 1,
         "安全阀动作灵活、复位密封无泄漏"),
        (7, "试运行与参数复检",
         "恢复供电，空载启动确认无异响；加载运行检查排气压力（0.7MPa）、"
         "排气温度（<95°C）、电流是否正常。",
         "异常振动或温度须立即停机排查。", "万用表, 温度计", 0, ""),
    ],
}

# 空压机设备台账
SEED_COMPRESSOR_DEVICES = [
    ("AC-7001", "复盛 SA37 螺杆空压机", "螺杆空压机", "LS25-132",
     "动力车间 1 号位", "normal", 720, "1 号空压机，日运行 12 小时",
     [
        ("排气压力不足", "排气压力仅 0.55MPa，低于设定值。",
         "清洗进气阀阀芯积碳，更换密封圈。", "serious", "done", 55),
        ("排气温度偏高", "排气温度达 102°C，接近报警阈值。",
         "清洁冷却器翅片积灰，补充机油。", "general", "done", 20),
     ]),
    ("AC-7002", "复盛 SA37 螺杆空压机", "螺杆空压机", "LS25-132",
     "动力车间 2 号位", "normal", 700, "2 号空压机，备用机", []),
]

# 种子反馈/修正知识（M5 反馈增强闭环演示）
SEED_FEEDBACKS = [
    {
        "qa_query": "发动机怠速不稳怎么修",
        "answer_preview": "怠速不稳可能是化油器堵塞，建议清洗化油器。",
        "vote": "down",
        "correction_text": "补充关键排查顺序：应先检查火花塞电极颜色和间隙（0.6~0.7mm），"
                           "再检查气门间隙（进气0.05mm/排气0.08mm），最后才清洗化油器怠速油路。"
                           "忽略火花塞和气门间隙直接洗化油器是常见误区。",
        "pub_status": "published",
    },
    {
        "qa_query": "空压机排气压力低是什么原因",
        "answer_preview": "可能是滤芯堵塞，更换滤芯即可。",
        "vote": "down",
        "correction_text": "排气压力低需按排查链路逐步检查：1) 滤芯压差（>0.05MPa才需换）；"
                           "2) 进气阀动作是否灵活（最常见原因）；3) 最小压力阀；4) 管路泄漏。"
                           "直接换滤芯而不检查进气阀会遗漏主要故障点。",
        "pub_status": "published",
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

# 种子设备台账（增强 G1 一机一档）：同型号「通用四冲程」便于软关联现有案例/SOP；
# 报修记录刻意让「怠速不稳」高频复发，为故障预警（G6）提供素材。
# 每台：(资产编号, 名称, 类型, 型号, 位置, 状态, 投运天数前, 备注, 报修列表)
# 报修：(标题, 故障描述, 处理措施, 严重度, 状态, 距今天数)
SEED_DEVICES = [
    ("MTO-2301", "本田 CG125 教学台架发动机", "摩托车发动机", "通用四冲程",
     "实训楼 A-101", "normal", 540, "教学用一号台架，使用频率高",
     [
         ("怠速不稳、易熄火", "冷车怠速抖动明显，补油后恢复。",
          "清洗化油器怠速油路，更换火花塞并校正间隙。", "general", "done", 86),
         ("怠速再次不稳", "运行约两周后怠速不稳复发。",
          "复查化油器，清理怠速量孔油泥并重新调整混合比。", "serious", "done", 41),
         ("火花塞积碳发黑", "动力下降，拆检火花塞电极积碳。",
          "更换同型号火花塞，建议缩短保养周期。", "general", "done", 12),
     ]),
    ("MTO-2302", "雅马哈 YBR125 实训发动机", "摩托车发动机", "通用四冲程",
     "实训楼 A-102", "repairing", 420, "二号台架",
     [
         ("连续运行后过热", "连续骑行后发动机过热、动力下降。",
          "清理风冷散热片泥垢，补充机油至标准液位。", "serious", "done", 60),
         ("气门室异响", "冷启动有规律'嗒嗒'金属敲击声，疑气门间隙过大。",
          "", "urgent", "open", 2),
     ]),
    ("MTO-2303", "通用四冲程教学发动机", "摩托车发动机", "通用四冲程",
     "实训楼 B-201", "stopped", 300, "三号台架，当前停用待保养", []),
]

# =========================================================================
# 第三设备类型：数控机床（CNC）—— 扩充知识库覆盖面
# =========================================================================
SEED_CNC_DOC = {
    "title": "数控车床维修手册（节选）",
    "source_type": "manual",
    "device_model": "CK6140",
    "device_type": "数控机床",
}

SEED_CNC_CHUNKS = [
    (6, "数控车床主轴轴承更换与预紧：主轴轴承采用精密角接触球轴承，"
        "更换时须配对选型，内外圈配合间隙 0.003~0.005mm。"
        "预紧力通过内外隔套厚度差实现，过盈量过大导致发热、过小导致刚性不足。"
        "装配后用手转动主轴应无卡滞、无异常噪声。"),
    (12, "主轴异响故障诊断：主轴运转时出现周期性'咔咔'声，常见原因："
        "1) 轴承磨损或滚珠剥落；2) 齿轮啮合间隙过大；3) 皮带轮松动或不平衡。"
        "低速有响声高速消失多为齿轮问题；各转速均有响声且伴有振动多为轴承问题。"
        "用听诊棒定位声源，振动分析仪检测频谱特征。"),
    (20, "数控系统报警处理：常见报警代码及含义——"
        "EX1001 急停信号触发：检查急停按钮与限位开关；"
        "EX2003 主轴过载：检查切削参数与主轴电机散热；"
        "EX3005 X轴伺服通讯异常：检查伺服驱动器与数控系统连接线缆。"
        "报警清除后须记录现象与处理过程，便于积累诊断经验。"),
    (28, "伺服驱动器维护：伺服驱动器是数控机床的核心控制单元。"
        "定期检查：1) 散热风扇运转是否正常；2) 电容是否鼓包漏液；"
        "3) 接线端子是否松动发热；4) 参数是否被意外修改。"
        "驱动器过流报警须排查电机绝缘、编码器线缆与机械负载。"),
    (35, "滚珠丝杠维护与故障排查：滚珠丝杠是将伺服电机旋转转化为直线运动的精密部件。"
        "常见故障：反向间隙过大（丝杠磨损或预紧力消失）、丝杠螺母异响（滚珠破损或润滑不良）、"
        "丝杠温升过高（预紧过大或润滑不足）。反向间隙补偿值超过 0.05mm 须机械调整。"),
    (42, "数控机床精度检测与补偿：定期检测定位精度、重复定位精度与反向间隙。"
        "使用激光干涉仪检测全行程定位精度，标准为 0.015mm/300mm。"
        "反向间隙用千分表检测，超过 0.02mm 须调整丝杠预紧或螺母座。"
        "螺距误差通过数控系统螺距补偿功能修正。"),
    (50, "液压系统故障排查：数控机床液压系统用于卡盘夹紧、尾座顶紧等。"
        "常见故障：1) 系统压力不足（泵磨损或溢流阀泄漏）；2) 油温过高（散热器堵塞或油液变质）；"
        "3) 执行元件爬行（油中混入空气或密封件老化）。定期检查油液清洁度与液位。"),
    (56, "冷却系统维护：切削液系统包含水箱、水泵、管路与喷嘴。"
        "常见故障：1) 流量不足（水泵叶轮磨损或滤网堵塞）；2) 切削液变质发臭（需更换并清洗水箱）；"
        "3) 管路泄漏（接头松动或软管老化）。建议每季度更换切削液并彻底清洗水箱。"),
]

SEED_CNC_CASES = [
    {
        "title": "数控车床主轴轴承异响故障案例",
        "device_type": "数控机床",
        "device_model": "CK6140",
        "content": "故障现象：CK6140 数控车床主轴在 800rpm 运转时出现明显'咔咔'异响，"
                   "伴有主轴箱振动增大，加工表面粗糙度超标。"
                   "排查过程：用听诊棒定位声源在主轴后轴承处；振动分析仪检测出外圈故障频率；"
                   "拆检发现角接触球轴承外圈滚道有剥落坑。"
                   "处理措施：更换配对精密角接触球轴承，调整预紧隔套厚度至规定值。"
                   "空运行 2 小时温升正常，复加工工件合格。",
        "kg": {
            "entities": [
                {"name": "数控机床", "etype": "device"},
                {"name": "主轴", "etype": "part"},
                {"name": "主轴轴承", "etype": "part"},
                {"name": "主轴异响", "etype": "fault"},
                {"name": "轴承磨损", "etype": "cause"},
                {"name": "滚道剥落", "etype": "cause"},
                {"name": "更换轴承", "etype": "measure"},
                {"name": "调整预紧", "etype": "measure"},
            ],
            "relations": [
                {"source": "数控机床", "rel": "包含", "target": "主轴"},
                {"source": "主轴", "rel": "包含", "target": "主轴轴承"},
                {"source": "数控机床", "rel": "发生", "target": "主轴异响"},
                {"source": "主轴异响", "rel": "源于", "target": "轴承磨损"},
                {"source": "轴承磨损", "rel": "源于", "target": "滚道剥落"},
                {"source": "主轴异响", "rel": "采取", "target": "更换轴承"},
                {"source": "主轴异响", "rel": "采取", "target": "调整预紧"},
            ],
        },
    },
    {
        "title": "数控车床X轴反向间隙过大故障案例",
        "device_type": "数控机床",
        "device_model": "CK6140",
        "content": "故障现象：CK6140 数控车床加工圆弧时表面有明显刀痕，"
                   "千分表检测X轴反向间隙达 0.08mm（标准≤0.02mm）。"
                   "排查过程：检查丝杠螺母座无松动；手动转动丝杠感觉有窜动；"
                   "拆检发现滚珠丝杠螺母预紧碟簧失效。"
                   "处理措施：更换碟簧组并重新预紧，用千分表复测反向间隙降至 0.01mm。"
                   "加工圆弧刀痕消失，精度恢复正常。",
        "kg": {
            "entities": [
                {"name": "滚珠丝杠", "etype": "part"},
                {"name": "反向间隙过大", "etype": "fault"},
                {"name": "预紧失效", "etype": "cause"},
                {"name": "碟簧损坏", "etype": "cause"},
                {"name": "更换碟簧", "etype": "measure"},
                {"name": "重新预紧", "etype": "measure"},
            ],
            "relations": [
                {"source": "数控机床", "rel": "包含", "target": "滚珠丝杠"},
                {"source": "数控机床", "rel": "发生", "target": "反向间隙过大"},
                {"source": "反向间隙过大", "rel": "源于", "target": "预紧失效"},
                {"source": "预紧失效", "rel": "源于", "target": "碟簧损坏"},
                {"source": "反向间隙过大", "rel": "采取", "target": "更换碟簧"},
                {"source": "反向间隙过大", "rel": "采取", "target": "重新预紧"},
            ],
        },
    },
    {
        "title": "数控车床伺服驱动器过流报警案例",
        "device_type": "数控机床",
        "device_model": "CK6140",
        "content": "故障现象：CK6140 数控车床Z轴移动时频繁报伺服过流（EX4001），"
                   "重置后可短暂恢复但很快再次报警。"
                   "排查过程：检查Z轴伺服电机绝缘电阻正常（≥50MΩ）；"
                   "断开机械负载后电机空转不报警，说明机械侧卡阻；"
                   "检查发现Z轴导轨润滑不良导致阻力增大。"
                   "处理措施：清洗导轨油路、更换润滑脂，手动打油至各润滑点。"
                   "Z轴移动顺畅，过流报警消除。",
        "kg": {
            "entities": [
                {"name": "伺服驱动器", "etype": "part"},
                {"name": "导轨", "etype": "part"},
                {"name": "伺服过流", "etype": "fault"},
                {"name": "导轨润滑不良", "etype": "cause"},
                {"name": "机械阻力增大", "etype": "cause"},
                {"name": "清洗导轨", "etype": "measure"},
                {"name": "更换润滑脂", "etype": "measure"},
            ],
            "relations": [
                {"source": "数控机床", "rel": "包含", "target": "伺服驱动器"},
                {"source": "数控机床", "rel": "包含", "target": "导轨"},
                {"source": "数控机床", "rel": "发生", "target": "伺服过流"},
                {"source": "伺服过流", "rel": "源于", "target": "机械阻力增大"},
                {"source": "机械阻力增大", "rel": "源于", "target": "导轨润滑不良"},
                {"source": "伺服过流", "rel": "采取", "target": "清洗导轨"},
                {"source": "伺服过流", "rel": "采取", "target": "更换润滑脂"},
            ],
        },
    },
]

SEED_CNC_SOP = {
    "name": "数控车床定期维护标准作业流程",
    "device_type": "数控机床",
    "device_model": "CK6140",
    "repair_level": "二级维护",
    "summary": "适用于 CK6140 数控车床的定期二级维护，涵盖主轴、伺服系统、丝杠、导轨等关键项。",
    "steps": [
        (1, "安全准备", "断开主电源并上锁，确认数控系统完全断电；清理工作区域。",
         "带电操作有触电风险", "绝缘手套/安全帽", 1, "主电源已断开并上锁"),
        (2, "主轴系统检查", "检查主轴轴承温升（≤40°C）与异响；检查主轴端面跳动（≤0.01mm）。",
         "主轴运转时禁止触碰", "百分表/测温仪", 1, "主轴跳动与温升合格"),
        (3, "伺服系统检查", "检查各轴伺服电机温升与噪音；检查驱动器参数与报警记录。",
         "伺服系统带高压", "万用表/测温仪", 1, "各轴伺服无异常报警"),
        (4, "滚珠丝杠维护", "检查丝杠润滑与反向间隙（≤0.02mm）；清理丝杠防护罩。",
         "丝杠运行时禁止触碰", "千分表/润滑脂", 0, ""),
        (5, "导轨润滑", "检查导轨油路是否通畅；手动注油器打油至各润滑点。",
         "油液滑倒风险", "润滑脂/油枪", 0, ""),
        (6, "精度检测", "用激光干涉仪检测定位精度；用千分表检测反向间隙。",
         "检测时须空载", "激光干涉仪/千分表", 1, "精度检测报告归档"),
        (7, "冷却系统维护", "检查切削液浓度与pH值；清洁水泵滤网；检查管路密封。",
         "切削液接触皮肤", "pH试纸/扳手", 0, ""),
        (8, "清理与复位", "清洁机床内外，恢复防护罩；通电试运行各轴移动正常后交付。",
         "试运行须人员撤离", "清洁工具", 1, "试运行正常、维护记录归档"),
    ],
}

SEED_CNC_DEVICES = [
    ("CNC-1001", "CK6140 数控车床（一号）", "数控机床", "CK6140",
     "金工车间 A 区", "normal", 900, "主力加工设备",
     [
         ("主轴异响", "800rpm运转时出现咔咔异响，振动增大。",
          "更换主轴后轴承并调整预紧。", "serious", "done", 30),
         ("X轴反向间隙大", "加工圆弧有刀痕，反向间隙0.08mm。",
          "更换碟簧组重新预紧。", "general", "done", 15),
     ]),
    ("CNC-1002", "CK6140 数控车床（二号）", "数控机床", "CK6140",
     "金工车间 B 区", "repairing", 600, "二号设备",
     [
         ("Z轴伺服过流", "Z轴移动频繁报伺服过流。",
          "", "urgent", "open", 3),
     ]),
]

# 额外摩托车知识片段（大幅扩充手册覆盖面至50+条）
SEED_EXTRA_MOTO_CHUNKS_2 = [
    (62, "点火系统故障诊断：磁电机点火系统常见故障为点火线圈次级短路、"
         "触发线圈阻值异常、CDI 点火器内部电子元件损坏。"
         "用万用表测点火线圈初级阻值（0.5~1.5Ω）、次级阻值（4~8kΩ），"
         "触发线圈阻值约 100~200Ω，偏差超标须更换。"),
    (68, "化油器深度清洗与调整：化油器分解后用超声波清洗仪清洗各油路气路，"
         "压缩空气吹通所有量孔。主量孔号数增大混合气变浓，减小变稀。"
         "怠速混合比调整螺钉标准拧入圈数为 1.5~2.5 圈，顺时针变稀、逆时针变浓。"),
    (75, "气缸磨损检测与修复：用量缸表测量气缸内径，在活塞销方向和垂直方向各取上中下三处。"
         "椭圆度超过 0.05mm 或锥度超过 0.10mm 须镗缸修复或更换缸体。"
         "镗缸后配加大活塞和活塞环，配合间隙 0.03~0.05mm。"),
    (82, "活塞环更换与对口：活塞环开口间隙标准 0.15~0.30mm，"
         "装入气缸后各环开口须错开 120°，且避开活塞销孔方向。"
         "第一道环为镀铬环（标记朝上），第二道环为普通铸铁环。"
         "环开口间隙过小会热膨胀卡死、过大会漏气导致功率下降。"),
    (88, "曲轴轴承检查与更换：曲轴左右轴承用塞尺检查径向游隙，"
         "超过 0.05mm 或转动有卡顿须更换。拆卸时用专用拉马，"
         "禁止用铁锤直接敲击。安装时加热轴承座至 120°C 热装或用专用套筒压入。"
         "轴承安装后须手动转动曲轴检查有无卡滞。"),
    (95, "离合器摩擦片测量：摩擦片标准厚度 3.0mm，磨损极限 2.6mm。"
         "用千分尺测量每片摩擦片厚度，任一片低于极限值须整组更换。"
         "离合器弹簧自由长度标准 35.5mm，极限 34.0mm，弹力减弱会导致打滑。"
         "组装时摩擦片与钢片交替排列，注意安装方向标记。"),
    (102, "变速箱齿轮检查：检查齿轮啮合面有无点蚀、剥落和裂纹。"
         "拨叉与齿轮槽间隙标准 0.2~0.4mm，超过 0.6mm 须更换拨叉。"
         "变速鼓凸轮槽磨损会导致换挡不准或脱挡。组装后检查各挡位切换是否顺畅。"),
    (108, "电气系统基础检测：蓄电池标准电压 12.6V（满充），低于 12.0V 须充电。"
         "磁电机充电线圈输出交流电压 13~18V（5000rpm），经整流器输出直流 13.5~14.5V。"
         "整流器损坏会导致蓄电池不充电或过充。用万用表检测充电电压判断故障点。"),
    (115, "进排气系统维护：空气滤芯每 3000km 清洁一次（纸质滤芯用压缩空气由内向外吹净），"
         "每 6000km 更换。排气管积碳过多会导致排气阻力增大、动力下降。"
         "消声器芯可定期用火烧法清除积碳（不锈钢芯）。进气漏气会导致混合气变稀。"),
    (120, "化油器真空膜片检查：CV 型化油器真空膜片破损会导致节气门无法正常提起，"
         "表现为加速无力或回火。拆下化油器顶盖取出真空柱塞，检查膜片有无裂纹穿孔。"
         "膜片破损须更换整个真空柱塞组件，安装时注意膜片定位销孔对正。"),
    (125, "发动机装配扭矩规范：气缸盖螺母 24N·m（按对角线分三次拧紧），"
         "磁电机飞轮螺母 60N·m，离合器锁紧螺母 45N·m，"
         "曲轴箱螺栓 10N·m。使用扭矩扳手按规定力矩拧紧，过紧会导致螺纹损坏、"
         "过松会导致松动漏油。铝螺纹孔须特别注意力矩控制。"),
    (130, "发动机大修后的磨合：新换活塞环、气缸、轴承等主要部件后须磨合。"
         "磨合期 500km 内：1) 避免急加速和全油门；2) 转速不超过 6000rpm；"
         "3) 变换车速避免长期同一转速。磨合后更换机油，检查各紧固件有无松动。"
         "磨合期操作不当会导致早期磨损和密封不良。"),
]

# 额外空压机知识片段
SEED_EXTRA_COMPRESSOR_CHUNKS = [
    (44, "空压机卸载阀工作原理：卸载阀在达到设定压力上限时打开，"
         "使空压机卸载运行（不产气、低功耗）。压力降至下限时关闭恢复加载。"
         "卸载阀故障表现为：压力到上限不停机（浪费电能）或频繁加卸载（磨损加快）。"
         "调节弹簧预紧力可改变加卸载压力设定值。"),
    (50, "空压机联轴器检查：电机与主机通过弹性联轴器连接。"
         "检查项目：1) 弹性块有无磨损开裂（磨损超过 2mm 须更换）；"
         "2) 电机与主机轴对中误差（径向≤0.05mm，角向≤0.05mm/100mm）；"
         "3) 联轴器螺栓有无松动。对中不良会导致弹性块快速磨损和轴承异常受力。"),
    (56, "空压机最小压力阀故障：最小压力阀确保系统油压在 0.4MPa 以上才向外供气。"
         "故障现象：1) 开机即喷油（阀芯卡在开启位）；2) 排气压力上不去（阀芯卡死关闭）。"
         "拆检阀芯弹簧与密封圈，清洗或更换损坏件。"),
    (62, "空压机电气控制柜维护：检查接触器触点有无烧蚀（接触电阻≤0.5Ω），"
         "热继电器整定电流是否匹配电机额定电流。PLC 控制器须检查输入输出指示灯、"
         "传感器接线端子是否紧固。变频空压机须检查变频器散热风扇与滤波电容。"),
]

# 额外数控机床知识片段
SEED_EXTRA_CNC_CHUNKS = [
    (60, "数控机床编码器维护：编码器是伺服系统的位置反馈元件。"
         "常见故障：信号丢失（联轴器松动或编码器线缆断线）、精度下降（码盘污染）。"
         "维护：定期检查编码器联轴器紧固、线缆弯曲半径≥10倍线径、"
         "用无水乙醇清洁码盘（禁止用手直接触碰）。"),
    (66, "数控机床回零故障排查：各轴回参考点时找不到零位或位置偏移，常见原因："
         "1) 减速开关位置偏移；2) 编码器零位脉冲丢失；3) 回零参数被修改。"
         "排查：手动检查减速开关动作（万用表通断挡），用示波器检测编码器零脉冲信号，"
         "核对数控系统回零参数。"),
]

# 额外反馈修正知识
SEED_EXTRA_FEEDBACKS = [
    {
        "qa_query": "数控车主轴异响是什么原因",
        "answer_preview": "可能是轴承有问题，换个轴承就行。",
        "vote": "down",
        "correction_text": "主轴异响需区分原因：低速有响高速消失多为齿轮问题；"
                           "各转速均有响且伴振动多为轴承问题。须用听诊棒定位声源、"
                           "振动分析仪检测频谱特征后再判断。直接换轴承而不做频谱分析"
                           "可能误判，且换装后须调整预紧隔套厚度。",
        "pub_status": "published",
    },
    {
        "qa_query": "发动机过热怎么处理",
        "answer_preview": "过热就是水不够了，加水就行。",
        "vote": "down",
        "correction_text": "风冷发动机过热常见原因：散热片堵塞、机油不足、点火过迟。"
                           "应先检查散热片是否被泥垢堵塞（最常见），再检查机油量与品质，"
                           "最后检查点火正时。持续过热会导致拉缸等严重故障，不能简单加水。"
                           "摩托车是风冷发动机，没有水冷系统。",
        "pub_status": "published",
    },
    {
        "qa_query": "X轴反向间隙大了怎么办",
        "answer_preview": "在系统里把反向间隙补偿值调大就行。",
        "vote": "down",
        "correction_text": "反向间隙补偿只是软件手段，超过 0.05mm 须做机械调整。"
                           "排查顺序：1) 检查丝杠螺母座有无松动；2) 检查丝杠预紧碟簧是否失效；"
                           "3) 检查丝杠本身磨损程度。软件补偿不能替代机械修复，"
                           "补偿值越来越大说明机械磨损在加剧，须及时检修。",
        "pub_status": "published",
    },
]

# 额外摩托车检修案例（扩充案例库至15+）
SEED_EXTRA_MOTO_CASES = [
    {
        "title": "发动机启动困难故障检修案例",
        "device_type": "摩托车发动机",
        "device_model": "通用四冲程",
        "content": "故障现象：冷车启动困难，电启动需按 5 秒以上才能着车，热车启动正常。"
                   "排查过程：测量蓄电池电压 12.2V（偏低）；检查火花塞电极发白（混合气过稀）；"
                   "检查化油器阻风门发现膜片破裂无法关闭。"
                   "处理措施：更换阻风门膜片、充电至 12.8V、调整混合比螺钉至 2 圈。"
                   "冷车启动 1 秒着车，故障排除。",
        "kg": {
            "entities": [
                {"name": "启动困难", "etype": "fault"},
                {"name": "混合气过稀", "etype": "cause"},
                {"name": "阻风门膜片破裂", "etype": "cause"},
                {"name": "更换膜片", "etype": "measure"},
                {"name": "调整混合比", "etype": "measure"},
            ],
            "relations": [
                {"source": "摩托车发动机", "rel": "发生", "target": "启动困难"},
                {"source": "启动困难", "rel": "源于", "target": "混合气过稀"},
                {"source": "混合气过稀", "rel": "源于", "target": "阻风门膜片破裂"},
                {"source": "启动困难", "rel": "采取", "target": "更换膜片"},
                {"source": "启动困难", "rel": "采取", "target": "调整混合比"},
            ],
        },
    },
    {
        "title": "离合器打滑故障检修案例",
        "device_type": "摩托车发动机",
        "device_model": "通用四冲程",
        "content": "故障现象：加速时发动机转速升高但车速不跟，上坡尤为明显。"
                   "排查过程：检查离合器拉索自由行程 2mm（正常）；"
                   "拆检摩擦片厚度 2.4mm（低于极限 2.6mm）；检查弹簧自由长度 33.8mm（低于极限）。"
                   "处理措施：成套更换摩擦片与弹簧，组装后离合器接合顺畅，加速有力。"
                   "建议用户避免半离合长时间滑行以延长寿命。",
        "kg": {
            "entities": [
                {"name": "离合器打滑", "etype": "fault"},
                {"name": "摩擦片磨损", "etype": "cause"},
                {"name": "弹簧弹力减弱", "etype": "cause"},
                {"name": "更换摩擦片", "etype": "measure"},
                {"name": "更换弹簧", "etype": "measure"},
            ],
            "relations": [
                {"source": "摩托车发动机", "rel": "发生", "target": "离合器打滑"},
                {"source": "离合器打滑", "rel": "源于", "target": "摩擦片磨损"},
                {"source": "离合器打滑", "rel": "源于", "target": "弹簧弹力减弱"},
                {"source": "离合器打滑", "rel": "采取", "target": "更换摩擦片"},
                {"source": "离合器打滑", "rel": "采取", "target": "更换弹簧"},
            ],
        },
    },
    {
        "title": "变速箱异响故障检修案例",
        "device_type": "摩托车发动机",
        "device_model": "通用四冲程",
        "content": "故障现象：空挡时有持续'嗡嗡'声，踩下离合器消失，行驶中各挡均有异响。"
                   "排查过程：空挡异响+离合器分离消失，指向输入轴轴承；"
                   "行驶各挡均有响声，进一步指向主轴或副轴轴承。"
                   "拆解发现输入轴轴承内圈滚道点蚀。"
                   "处理措施：更换输入轴轴承（6204），检查变速箱齿轮无异常。"
                   "装复后异响消失。",
        "kg": {
            "entities": [
                {"name": "变速箱异响", "etype": "fault"},
                {"name": "输入轴轴承磨损", "etype": "cause"},
                {"name": "轴承点蚀", "etype": "cause"},
                {"name": "更换轴承", "etype": "measure"},
            ],
            "relations": [
                {"source": "摩托车发动机", "rel": "发生", "target": "变速箱异响"},
                {"source": "变速箱异响", "rel": "源于", "target": "输入轴轴承磨损"},
                {"source": "输入轴轴承磨损", "rel": "源于", "target": "轴承点蚀"},
                {"source": "变速箱异响", "rel": "采取", "target": "更换轴承"},
            ],
        },
    },
    {
        "title": "电气系统不充电故障检修案例",
        "device_type": "摩托车发动机",
        "device_model": "通用四冲程",
        "content": "故障现象：骑行中灯光变暗、喇叭音量小，蓄电池频繁亏电无法启动。"
                   "排查过程：万用表测蓄电池两端电压，发动机 5000rpm 时仅 11.8V（正常应 13.5~14.5V）；"
                   "测量磁电机充电线圈输出 15V（正常），说明线圈没问题；"
                   "检查整流器输出端无直流电压，判断整流器损坏。"
                   "处理措施：更换整流调节器，复测充电电压 14.2V，故障排除。",
        "kg": {
            "entities": [
                {"name": "不充电", "etype": "fault"},
                {"name": "整流器损坏", "etype": "cause"},
                {"name": "更换整流器", "etype": "measure"},
            ],
            "relations": [
                {"source": "摩托车发动机", "rel": "发生", "target": "不充电"},
                {"source": "不充电", "rel": "源于", "target": "整流器损坏"},
                {"source": "不充电", "rel": "采取", "target": "更换整流器"},
            ],
        },
    },
    {
        "title": "空压机过热停机故障案例",
        "device_type": "螺杆空压机",
        "device_model": "LS25-132",
        "content": "故障现象：LS25-132 空压机运行 20 分钟后排气温度达 105°C 自动停机。"
                   "排查过程：检查冷却器翅片积灰严重但未完全堵死；检查油位正常；"
                   "检查温控阀发现阀芯卡在部分开启位导致冷却油路流量不足。"
                   "处理措施：用压缩空气吹扫冷却器翅片，更换温控阀芯。"
                   "复机运行 2 小时排气温度稳定在 85°C。",
        "kg": {
            "entities": [
                {"name": "空压机过热", "etype": "fault"},
                {"name": "冷却器积灰", "etype": "cause"},
                {"name": "温控阀故障", "etype": "cause"},
                {"name": "清理冷却器", "etype": "measure"},
                {"name": "更换温控阀", "etype": "measure"},
            ],
            "relations": [
                {"source": "螺杆空压机", "rel": "发生", "target": "空压机过热"},
                {"source": "空压机过热", "rel": "源于", "target": "冷却器积灰"},
                {"source": "空压机过热", "rel": "源于", "target": "温控阀故障"},
                {"source": "空压机过热", "rel": "采取", "target": "清理冷却器"},
                {"source": "空压机过热", "rel": "采取", "target": "更换温控阀"},
            ],
        },
    },
    {
        "title": "空压机频繁加卸载故障案例",
        "device_type": "螺杆空压机",
        "device_model": "LS25-132",
        "content": "故障现象：空压机每 30 秒加卸载一次，产线用气量并无大幅波动。"
                   "排查过程：检查卸载阀设定压力正常；检查管路无大泄漏；"
                   "检查最小压力阀发现阀芯密封圈老化漏气，导致系统压力维持不住。"
                   "处理措施：更换最小压力阀密封圈，加卸载周期恢复正常（约 5 分钟/次）。",
        "kg": {
            "entities": [
                {"name": "频繁加卸载", "etype": "fault"},
                {"name": "最小压力阀泄漏", "etype": "cause"},
                {"name": "密封圈老化", "etype": "cause"},
                {"name": "更换密封圈", "etype": "measure"},
            ],
            "relations": [
                {"source": "螺杆空压机", "rel": "发生", "target": "频繁加卸载"},
                {"source": "频繁加卸载", "rel": "源于", "target": "最小压力阀泄漏"},
                {"source": "最小压力阀泄漏", "rel": "源于", "target": "密封圈老化"},
                {"source": "频繁加卸载", "rel": "采取", "target": "更换密封圈"},
            ],
        },
    },
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
                    reviewed_by=auditor.id,
                    reviewed_at=dt.datetime.now(tz=timezone.utc).replace(tzinfo=None),
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
                persist_extraction(db, case.id, sc["kg"], align=False)
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

        # --- 种子设备台账 + 报修记录（增强 G1，仅首次）---
        exists_dev = db.execute(select(Device)).first()
        if not exists_dev:
            worker = db.execute(
                select(User).where(User.username == "worker")
            ).scalar_one()
            auditor = db.execute(
                select(User).where(User.username == "auditor")
            ).scalar_one()
            now = dt.datetime.now(tz=timezone.utc).replace(tzinfo=None)
            dev_count = rec_count = 0
            for (code, name, dtype, model, loc, st, days_ago, note, recs) in SEED_DEVICES:
                d = Device(
                    code=code, name=name, device_type=dtype, device_model=model,
                    location=loc, status=st, note=note,
                    commissioned_at=now - dt.timedelta(days=days_ago),
                )
                db.add(d)
                db.flush()
                dev_count += 1
                for (title, fault, handling, sev, rstatus, r_days) in recs:
                    created = now - dt.timedelta(days=r_days)
                    db.add(MaintenanceRecord(
                        device_id=d.id, title=title, fault_desc=fault,
                        handling=handling, severity=sev, status=rstatus,
                        reporter_id=worker.id,
                        handler_id=(auditor.id if rstatus == "done" else None),
                        created_at=created,
                        done_at=(created + dt.timedelta(days=1) if rstatus == "done" else None),
                    ))
                    rec_count += 1
            db.commit()
            print(f"种子设备台账已写入（{dev_count} 台设备 + {rec_count} 条报修记录）。")
        else:
            print("种子设备已存在，跳过。")

        # --- 额外摩托车知识片段（补充手册覆盖面，仅首次）---
        moto_doc = db.execute(
            select(Document).where(Document.title == SEED_DOC["title"])
        ).scalar_one_or_none()
        if moto_doc and not db.execute(
            select(DocChunk).where(DocChunk.doc_id == moto_doc.id, DocChunk.page == 45)
        ).first():
            embedder = get_embedder()
            texts = [c[1] for c in SEED_EXTRA_MOTO_CHUNKS]
            vecs = embedder.embed(texts)
            for (page, content), vec in zip(SEED_EXTRA_MOTO_CHUNKS, vecs):
                db.add(DocChunk(doc_id=moto_doc.id, content=content,
                                page=page, embedding=vec))
            db.commit()
            print(f"摩托车额外知识片段已写入（{len(SEED_EXTRA_MOTO_CHUNKS)} 条）。")

        # --- 螺杆空压机手册 + SOP + 案例 + 设备（第二设备类型，仅首次）---
        if not db.execute(
            select(Document).where(Document.title == SEED_COMPRESSOR_DOC["title"])
        ).first():
            # 文档 + 分块
            doc = Document(**SEED_COMPRESSOR_DOC, status="approved")
            db.add(doc)
            db.flush()
            embedder = get_embedder()
            texts = [c[1] for c in SEED_COMPRESSOR_CHUNKS]
            vecs = embedder.embed(texts)
            for (page, content), vec in zip(SEED_COMPRESSOR_CHUNKS, vecs):
                db.add(DocChunk(doc_id=doc.id, content=content,
                                page=page, embedding=vec))
            db.commit()
            print(f"螺杆空压机手册已写入（{len(SEED_COMPRESSOR_CHUNKS)} 条分块）。")

            # SOP
            tpl = SOPTemplate(
                name=SEED_COMPRESSOR_SOP["name"],
                device_type=SEED_COMPRESSOR_SOP["device_type"],
                device_model=SEED_COMPRESSOR_SOP["device_model"],
                repair_level=SEED_COMPRESSOR_SOP["repair_level"],
                summary=SEED_COMPRESSOR_SOP["summary"],
                source="manual", status="approved",
            )
            db.add(tpl)
            db.flush()
            for order_no, title, instruction, risk, tools, req, cp in SEED_COMPRESSOR_SOP["steps"]:
                db.add(SOPStep(
                    template_id=tpl.id, order_no=order_no, title=title,
                    instruction=instruction, risk=risk, tools=tools,
                    is_required=req, checkpoint=cp,
                ))
            db.commit()
            print(f"空压机 SOP 已写入（{len(SEED_COMPRESSOR_SOP['steps'])} 步）。")

            # 案例 + 知识图谱
            worker = db.execute(
                select(User).where(User.username == "worker")
            ).scalar_one()
            auditor = db.execute(
                select(User).where(User.username == "auditor")
            ).scalar_one()
            sc = SEED_COMPRESSOR_CASE
            case = RepairCase(
                title=sc["title"], device_type=sc["device_type"],
                device_model=sc["device_model"], content=sc["content"],
                author_id=worker.id, status="approved",
                reviewed_by=auditor.id,
                reviewed_at=dt.datetime.now(tz=timezone.utc).replace(tzinfo=None),
                review_note="种子案例·空压机示例",
            )
            db.add(case)
            db.flush()
            cdoc = ingest_text(
                db, title=case.title, content=case.content,
                device_type=case.device_type, device_model=case.device_model,
                source_type="case", status="approved",
            )
            case.doc_id = cdoc.id
            persist_extraction(db, case.id, sc["kg"], align=False)
            db.commit()
            print("空压机案例 + 知识图谱已写入。")

            # 设备台账
            now = dt.datetime.now(tz=timezone.utc).replace(tzinfo=None)
            for (code, name, dtype, model, loc, st, days_ago, note, recs) in SEED_COMPRESSOR_DEVICES:
                d = Device(
                    code=code, name=name, device_type=dtype, device_model=model,
                    location=loc, status=st, note=note,
                    commissioned_at=now - dt.timedelta(days=days_ago),
                )
                db.add(d)
                db.flush()
                for (title, fault, handling, sev, rstatus, r_days) in recs:
                    created = now - dt.timedelta(days=r_days)
                    db.add(MaintenanceRecord(
                        device_id=d.id, title=title, fault_desc=fault,
                        handling=handling, severity=sev, status=rstatus,
                        reporter_id=worker.id,
                        handler_id=(auditor.id if rstatus == "done" else None),
                        created_at=created,
                        done_at=(created + dt.timedelta(days=1) if rstatus == "done" else None),
                    ))
            db.commit()
            print(f"空压机设备台账已写入（{len(SEED_COMPRESSOR_DEVICES)} 台）。")

        # --- 额外摩托车知识片段第二批（大幅扩充手册覆盖面，仅首次）---
        moto_doc = db.execute(
            select(Document).where(Document.title == SEED_DOC["title"])
        ).scalar_one_or_none()
        if moto_doc and not db.execute(
            select(DocChunk).where(DocChunk.doc_id == moto_doc.id, DocChunk.page == 62)
        ).first():
            embedder = get_embedder()
            texts = [c[1] for c in SEED_EXTRA_MOTO_CHUNKS_2]
            vecs = embedder.embed(texts)
            for (page, content), vec in zip(SEED_EXTRA_MOTO_CHUNKS_2, vecs):
                db.add(DocChunk(doc_id=moto_doc.id, content=content,
                                page=page, embedding=vec))
            db.commit()
            print(f"摩托车额外知识片段第二批已写入（{len(SEED_EXTRA_MOTO_CHUNKS_2)} 条）。")

        # --- 额外空压机知识片段（仅首次）---
        comp_doc = db.execute(
            select(Document).where(Document.title == SEED_COMPRESSOR_DOC["title"])
        ).scalar_one_or_none()
        if comp_doc and not db.execute(
            select(DocChunk).where(DocChunk.doc_id == comp_doc.id, DocChunk.page == 44)
        ).first():
            embedder = get_embedder()
            texts = [c[1] for c in SEED_EXTRA_COMPRESSOR_CHUNKS]
            vecs = embedder.embed(texts)
            for (page, content), vec in zip(SEED_EXTRA_COMPRESSOR_CHUNKS, vecs):
                db.add(DocChunk(doc_id=comp_doc.id, content=content,
                                page=page, embedding=vec))
            db.commit()
            print(f"空压机额外知识片段已写入（{len(SEED_EXTRA_COMPRESSOR_CHUNKS)} 条）。")

        # --- 数控机床手册 + SOP + 案例 + 设备（第三设备类型，仅首次）---
        if not db.execute(
            select(Document).where(Document.title == SEED_CNC_DOC["title"])
        ).first():
            # 文档 + 分块
            doc = Document(**SEED_CNC_DOC, status="approved")
            db.add(doc)
            db.flush()
            embedder = get_embedder()
            all_cnc_chunks = SEED_CNC_CHUNKS + SEED_EXTRA_CNC_CHUNKS
            texts = [c[1] for c in all_cnc_chunks]
            vecs = embedder.embed(texts)
            for (page, content), vec in zip(all_cnc_chunks, vecs):
                db.add(DocChunk(doc_id=doc.id, content=content,
                                page=page, embedding=vec))
            db.commit()
            print(f"数控机床手册已写入（{len(all_cnc_chunks)} 条分块）。")

            # SOP
            tpl = SOPTemplate(
                name=SEED_CNC_SOP["name"],
                device_type=SEED_CNC_SOP["device_type"],
                device_model=SEED_CNC_SOP["device_model"],
                repair_level=SEED_CNC_SOP["repair_level"],
                summary=SEED_CNC_SOP["summary"],
                source="manual", status="approved",
            )
            db.add(tpl)
            db.flush()
            for order_no, title, instruction, risk, tools, req, cp in SEED_CNC_SOP["steps"]:
                db.add(SOPStep(
                    template_id=tpl.id, order_no=order_no, title=title,
                    instruction=instruction, risk=risk, tools=tools,
                    is_required=req, checkpoint=cp,
                ))
            db.commit()
            print(f"数控机床 SOP 已写入（{len(SEED_CNC_SOP['steps'])} 步）。")

            # 案例 + 知识图谱
            worker = db.execute(
                select(User).where(User.username == "worker")
            ).scalar_one()
            auditor = db.execute(
                select(User).where(User.username == "auditor")
            ).scalar_one()
            for sc in SEED_CNC_CASES:
                case = RepairCase(
                    title=sc["title"], device_type=sc["device_type"],
                    device_model=sc["device_model"], content=sc["content"],
                    author_id=worker.id, status="approved",
                    reviewed_by=auditor.id,
                    reviewed_at=dt.datetime.now(tz=timezone.utc).replace(tzinfo=None),
                    review_note="种子案例·数控机床示例",
                )
                db.add(case)
                db.flush()
                cdoc = ingest_text(
                    db, title=case.title, content=case.content,
                    device_type=case.device_type, device_model=case.device_model,
                    source_type="case", status="approved",
                )
                case.doc_id = cdoc.id
                persist_extraction(db, case.id, sc["kg"], align=False)
                db.commit()
            print(f"数控机床案例 + 知识图谱已写入（{len(SEED_CNC_CASES)} 条）。")

            # 设备台账
            now = dt.datetime.now(tz=timezone.utc).replace(tzinfo=None)
            for (code, name, dtype, model, loc, st, days_ago, note, recs) in SEED_CNC_DEVICES:
                d = Device(
                    code=code, name=name, device_type=dtype, device_model=model,
                    location=loc, status=st, note=note,
                    commissioned_at=now - dt.timedelta(days=days_ago),
                )
                db.add(d)
                db.flush()
                for (title, fault, handling, sev, rstatus, r_days) in recs:
                    created = now - dt.timedelta(days=r_days)
                    db.add(MaintenanceRecord(
                        device_id=d.id, title=title, fault_desc=fault,
                        handling=handling, severity=sev, status=rstatus,
                        reporter_id=worker.id,
                        handler_id=(auditor.id if rstatus == "done" else None),
                        created_at=created,
                        done_at=(created + dt.timedelta(days=1) if rstatus == "done" else None),
                    ))
            db.commit()
            print(f"数控机床设备台账已写入（{len(SEED_CNC_DEVICES)} 台）。")

        # --- 额外检修案例（扩充案例库至15+，仅首次）---
        if not db.execute(
            select(RepairCase).where(RepairCase.title == "发动机启动困难故障检修案例")
        ).first():
            worker = db.execute(
                select(User).where(User.username == "worker")
            ).scalar_one()
            auditor = db.execute(
                select(User).where(User.username == "auditor")
            ).scalar_one()
            for sc in SEED_EXTRA_MOTO_CASES:
                case = RepairCase(
                    title=sc["title"], device_type=sc["device_type"],
                    device_model=sc["device_model"], content=sc["content"],
                    author_id=worker.id, status="approved",
                    reviewed_by=auditor.id,
                    reviewed_at=dt.datetime.now(tz=timezone.utc).replace(tzinfo=None),
                    review_note="种子案例·扩充示例",
                )
                db.add(case)
                db.flush()
                cdoc = ingest_text(
                    db, title=case.title, content=case.content,
                    device_type=case.device_type, device_model=case.device_model,
                    source_type="case", status="approved",
                )
                case.doc_id = cdoc.id
                persist_extraction(db, case.id, sc["kg"], align=False)
                db.commit()
            print(f"额外检修案例已写入（{len(SEED_EXTRA_MOTO_CASES)} 条）。")

        # --- 种子反馈/修正知识（M5 反馈增强闭环，仅首次）---
        if not db.execute(select(LLMFeedback)).first():
            worker = db.execute(
                select(User).where(User.username == "worker")
            ).scalar_one()
            embedder = get_embedder()
            all_feedbacks = SEED_FEEDBACKS + SEED_EXTRA_FEEDBACKS
            for fb in all_feedbacks:
                # 先建一条 QA 日志作为反馈的关联对象
                qa = QALog(
                    user_id=worker.id, query=fb["qa_query"],
                    modality="text", answer=fb["answer_preview"],
                )
                db.add(qa)
                db.flush()
                # 生成问题向量用于反馈增强召回
                qvec = embedder.embed_one(fb["qa_query"])
                db.add(LLMFeedback(
                    qa_id=qa.id, user_id=worker.id, vote=fb["vote"],
                    correction_text=fb["correction_text"],
                    query=fb["qa_query"], query_embedding=qvec,
                    status="active", pub_status=fb["pub_status"], version=1,
                ))
            db.commit()
            print(f"种子反馈/修正知识已写入（{len(all_feedbacks)} 条）。")

        # --- 种子审计日志（进阶，仅首次）：还原种子操作的审计痕迹，开箱即演示 ---
        from .models import AuditLog
        if not db.execute(select(AuditLog)).first():
            au = db.execute(select(User).where(User.username == "auditor")).scalar_one()
            ad = db.execute(select(User).where(User.username == "admin")).scalar_one()
            seed_audits = [
                (ad, "sop.create", "sop", "新建并发布作业流程「摩托车发动机二级维护标准作业流程」"),
                (au, "case.approve", "case", "采纳案例「怠速不稳故障检修案例」并入库、抽取知识图谱"),
                (au, "case.approve", "case", "采纳案例「发动机过热故障检修案例」并入库、抽取知识图谱"),
                (ad, "device.create", "device", "设备建档「本田 CG125 教学台架发动机」（MTO-2301）"),
                (ad, "sop.create", "sop", "新建并发布作业流程「螺杆空压机定期维护标准作业流程」"),
                (au, "case.approve", "case", "采纳案例「螺杆空压机排气压力不足故障案例」并入库、抽取知识图谱"),
                (ad, "device.create", "device", "设备建档「复盛 SA37 螺杆空压机」（AC-7001）"),
                (ad, "sop.create", "sop", "新建并发布作业流程「数控车床定期维护标准作业流程」"),
                (au, "case.approve", "case", "采纳案例「数控车床主轴轴承异响故障案例」并入库、抽取知识图谱"),
                (au, "case.approve", "case", "采纳案例「数控车床X轴反向间隙过大故障案例」并入库、抽取知识图谱"),
                (ad, "device.create", "device", "设备建档「CK6140 数控车床（一号）」（CNC-1001）"),
            ]
            for u, action, ttype, detail in seed_audits:
                db.add(AuditLog(user_id=u.id, username=u.display_name,
                                action=action, target_type=ttype, detail=detail))
            db.commit()
            print(f"种子审计日志已写入（{len(seed_audits)} 条）。")
        else:
            print("种子审计日志已存在，跳过。")

        print("初始化完成。账号：worker/worker123, auditor/auditor123, admin/admin123")
    finally:
        db.close()


if __name__ == "__main__":
    run()
