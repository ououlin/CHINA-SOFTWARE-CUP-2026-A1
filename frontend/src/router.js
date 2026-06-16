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
      { path: 'dashboard', component: Dashboard, meta: { title: '运营数据看板' } },
      { path: 'chat', component: Chat, meta: { title: '智能检修问答' } },
      { path: 'devices', component: Devices, meta: { title: '设备健康档案' } },
      { path: 'alert', component: Alert, meta: { title: '故障预警 · 预测性维护' } },
      { path: 'scan', component: Scan, meta: { title: '扫码报修' } },
      { path: 'sop', component: SOP, meta: { title: '标准化作业指引' } },
      { path: 'cases', component: Cases, meta: { title: '检修案例与知识沉淀' } },
      { path: 'graph', component: Graph, meta: { title: '知识图谱' } },
      { path: 'feedback', component: Feedback, meta: { title: '标注与修正' } },
      { path: 'documents', component: Documents, meta: { title: '知识库' } },
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
