import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ArrowDown,
  ChatDotRound,
  Check,
  CircleCheck,
  CircleCheckFilled,
  CircleClose,
  Connection,
  Cpu,
  Document,
  Loading,
  MagicStick,
  Microphone,
  Monitor,
  Moon,
  Promotion,
  Right,
  Search,
  Select,
  Service,
  Share,
  Sunny,
  Tickets,
  Tools,
  UserFilled,
  View,
  Warning,
  WarningFilled,
  WarnTriangleFilled,
} from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './styles.css'

const app = createApp(App)

// 仅注册模板里真正用到的图标（28 个），替代原先整体注册约 290 个图标的方式。
const icons = {
  ArrowDown,
  ChatDotRound,
  Check,
  CircleCheck,
  CircleCheckFilled,
  CircleClose,
  Connection,
  Cpu,
  Document,
  Loading,
  MagicStick,
  Microphone,
  Monitor,
  Moon,
  Promotion,
  Right,
  Search,
  Select,
  Service,
  Share,
  Sunny,
  Tickets,
  Tools,
  UserFilled,
  View,
  Warning,
  WarningFilled,
  WarnTriangleFilled,
}
for (const [name, component] of Object.entries(icons)) {
  app.component(name, component)
}

app.use(createPinia())
app.use(router)
app.mount('#app')
