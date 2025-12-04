import api from './api'
import { Session, Message } from '../types'

export interface CreateSessionRequest {
  agent_id: number
  title?: string
}

export const sessionsApi = {
  getSessions: async () => {
    const response = await api.get<{ code: number; data: Session[]; message: string }>('/sessions')
    return response.data
  },

  createSession: async (data: CreateSessionRequest) => {
    const response = await api.post<{ code: number; data: Session; message: string }>('/sessions', data)
    return response.data
  },

  getSessionMessages: async (sessionId: string) => {
    const response = await api.get<{ code: number; data: Message[]; message: string }>(`/sessions/${sessionId}/messages`)
    return response.data
  },

  deleteSession: async (sessionId: string) => {
    const response = await api.delete<{ code: number; message: string }>(`/sessions/${sessionId}`)
    return response
  },
}

