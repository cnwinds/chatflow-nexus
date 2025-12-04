import { create } from 'zustand'
import { User } from '../types'
import { authApi } from '../services/auth'

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  login: (loginName: string, password: string) => Promise<void>
  logout: () => void
  checkAuth: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: (() => {
    try {
      const stored = localStorage.getItem('auth-storage')
      if (stored) {
        const parsed = JSON.parse(stored)
        return parsed.state?.user || null
      }
    } catch {}
    return null
  })(),
  token: (() => {
    try {
      const stored = localStorage.getItem('auth-storage')
      if (stored) {
        const parsed = JSON.parse(stored)
        return parsed.state?.token || null
      }
    } catch {}
    return null
  })(),
  isAuthenticated: (() => {
    try {
      const stored = localStorage.getItem('auth-storage')
      if (stored) {
        const parsed = JSON.parse(stored)
        return !!parsed.state?.token
      }
    } catch {}
    return false
  })(),

  login: async (loginName: string, password: string) => {
    const response = await authApi.login({ login_name: loginName, password })
    const token = response.token
    localStorage.setItem('token', token)
    
    // 获取用户信息
    const userResponse = await authApi.getCurrentUser()
    const state = {
      token,
      user: userResponse,
      isAuthenticated: true,
    }
    set(state)
    localStorage.setItem('auth-storage', JSON.stringify({ state }))
  },

  logout: () => {
    localStorage.removeItem('token')
    localStorage.removeItem('auth-storage')
    set({
      user: null,
      token: null,
      isAuthenticated: false,
    })
  },

  checkAuth: async () => {
    const token = localStorage.getItem('token')
    if (token) {
      try {
        const user = await authApi.getCurrentUser()
        const state = {
          token,
          user,
          isAuthenticated: true,
        }
        set(state)
        localStorage.setItem('auth-storage', JSON.stringify({ state }))
      } catch (error) {
        localStorage.removeItem('token')
        localStorage.removeItem('auth-storage')
        set({
          user: null,
          token: null,
          isAuthenticated: false,
        })
      }
    }
  },
}))

