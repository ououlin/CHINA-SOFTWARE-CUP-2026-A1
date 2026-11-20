import {
  DataBoard,
  ChatDotRound,
  Cpu,
  Monitor,
  WarningFilled,
  Postcard,
  Tickets,
  EditPen,
  Share,
  Star,
  Collection,
  Document,
} from '@element-plus/icons-vue'

// 单一导航数据源：桌面侧栏、移动抽屉与面包屑均由此配置驱动。
export const navigationSections = [
  {
    label: '现场作业',
    items: [
      { path: '/dashboard', label: '数据看板', icon: DataBoard },
      { path: '/chat', label: '智能检修问答', icon: ChatDotRound },
      { path: '/agent', label: 'Agent 诊断', icon: Cpu },
      { path: '/devices', label: '设备档案', icon: Monitor },
      { path: '/alert', label: '故障预警', icon: WarningFilled, tone: 'warning' },
      { path: '/scan', label: '扫码报修', icon: Postcard, tone: 'accent' },
      { path: '/sop', label: '作业指引', icon: Tickets },
    ],
  },
  {
    label: '知识与治理',
    items: [
      { path: '/cases', label: '知识沉淀', icon: EditPen },
      { path: '/graph', label: '知识图谱', icon: Share },
      { path: '/feedback', label: '标注修正', icon: Star },
      { path: '/documents', label: '知识库', icon: Collection },
      { path: '/audit', label: '操作审计', icon: Document, manageOnly: true },
    ],
  },
]

export const navigationItems = navigationSections.flatMap((section) => section.items)

