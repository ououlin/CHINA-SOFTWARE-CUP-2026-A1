import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from './store'

import Login from './views/Login.vue'
import Layout from './views/Layout.vue'
import Chat from './views/Chat.vue'
import Documents from './views/Documents.vue'
import SOP from './views/SOP.vue'

const routes = [
  { path: '/login', component: Login, meta: { public: true } },
  {
    path: '/',
    component: Layout,
    redirect: '/chat',
    children: [
      { path: 'chat', component: Chat, meta: { title: '智能检修问答' } },
      { path: 'sop', component: SOP, meta: { title: '标准化作业指引' } },
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
    return '/chat'
  }
})

export default router
