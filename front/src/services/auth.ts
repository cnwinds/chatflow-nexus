import api from './api'
import { User } from '../types'

export interface LoginRequest {
  login_name: string
  password: string
}

export interface LoginResponse {
  token: string
  expire: number
  user_id: number
}

export interface RegisterRequest {
  user_name: string
  login_name: string
  password: string
  mobile?: string
  login_type?: number
}

export const authApi = {
  login: async (data: LoginRequest) => {
    const response = await api.post<{ code: number; data: LoginResponse; message: string }>('/auth/login', data)
    return response.data
  },

  register: async (data: RegisterRequest) => {
    const response = await api.post<{ code: number; message: string }>('/auth/register', data)
    return response
  },

  getCurrentUser: async () => {
    const response = await api.get<{ code: number; data: User; message: string }>('/auth/me')
    return response.data
  },
}

