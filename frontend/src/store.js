import { defineStore } from 'pinia'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: JSON.parse(localStorage.getItem('user') || 'null'),
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
  },
  actions: {
    setAuth(data) {
      this.token = data.access_token
      this.user = {
        username: data.username,
        display_name: data.display_name,
        role: data.role,
      }
      localStorage.setItem('token', this.token)
      localStorage.setItem('user', JSON.stringify(this.user))
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      if (location.hash !== '#/login') location.hash = '#/login'
    },
  },
})
