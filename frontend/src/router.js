import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from './store'

import Login from './views/Login.vue'
import Layout from './views/Layout.vue'
import Chat from './views/Chat.vue'
import Documents from './views/Documents.vue'
import SOP from './views/SOP.vue'
import Cases from './views/Cases.vue'
import Graph from './views/Graph.vue'
import Feedback from './views/Feedback.vue'
import Devices from './views/Devices.vue'
import Dashboard from './views/Dashboard.vue'
import Alert from './views/Alert.vue'
import Scan from './views/Scan.vue'

const routes = [
  { path: '/login', component: Login, meta: { public: true } },
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', component: Dashboard, meta: { title: '运营数据看板', desc: '全局运营指标与数据趋势总览' } },
      { path: 'chat', component: Chat, meta: { title: '智能检修问答', desc: '多模态检索 · 多轮对话 · 语音问答 · 引用溯源' } },
      { path: 'devices', component: Devices, meta: { title: '设备健康档案', desc: '一机一档 · 检修时间线 · 检修报告' } },
      { path: 'alert', component: Alert, meta: { title: '故障预警 · 预测性维护', desc: '风险评分 · 高频故障识别 · AI 维护建议' } },
      { path: 'scan', component: Scan, meta: { title: '扫码报修', desc: '设备二维码 · 扫码 / 输入编号即报修' } },
      { path: 'sop', component: SOP, meta: { title: '标准化作业指引', desc: '步骤化推进 · 合规必检 · 个性化推送' } },
      { path: 'cases', component: Cases, meta: { title: '检修案例与知识沉淀', desc: '一线提交 · 审核入库 · 自动抽取图谱' } },
      { path: 'graph', component: Graph, meta: { title: '知识图谱', desc: '设备 / 部件 / 故障 / 原因 / 措施关系网络' } },
      { path: 'feedback', component: Feedback, meta: { title: '标注与修正', desc: '满意度统计 · 人工修正知识治理' } },
      { path: 'documents', component: Documents, meta: { title: '知识库', desc: '检修手册与案例文档管理' } },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isLoggedIn) {
    return '/login'
  }
  if (to.path === '/login' && auth.isLoggedIn) {
    return '/dashboard'
  }
})

export default router
