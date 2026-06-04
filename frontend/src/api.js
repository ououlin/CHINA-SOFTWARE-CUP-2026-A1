import axios from 'axios'
import { useAuthStore } from './store'

const api = axios.create({ baseURL: '/api' })

// 请求拦截：自动附带 JWT
api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

// 响应拦截：401 自动登出
api.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response && err.response.status === 401) {
      const auth = useAuthStore()
      auth.logout()
    }
    return Promise.reject(err)
  }
)

export default api
