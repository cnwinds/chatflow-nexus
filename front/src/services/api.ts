import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8020'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器：添加token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器：处理错误
api.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    if (error.response?.status === 401) {
      // Token过期，清除本地存储
      localStorage.removeItem('token')
      localStorage.removeItem('auth-storage')
      
      // 只在当前不在登录页时才跳转，避免循环刷新
      if (window.location.pathname !== '/login') {
        // 使用 window.location.replace 避免在历史记录中留下记录
        window.location.replace('/login')
      }
    }
    return Promise.reject(error)
  }
)

export default api

