import { create } from 'zustand'
import { Session, Message } from '../types'
import { sessionsApi } from '../services/sessions'

interface ChatState {
  currentSession: Session | null
  sessions: Session[]
  messages: Message[]
  setCurrentSession: (session: Session | null) => void
  loadSessions: () => Promise<void>
  loadMessages: (sessionId: string) => Promise<Message[]>
  addMessage: (message: Message) => void
  updateMessage: (id: number, updates: Partial<Message>) => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  currentSession: null,
  sessions: [],
  messages: [],

  setCurrentSession: (session) => {
    set({ currentSession: session })
    if (session) {
      get().loadMessages(session.session_id)
    }
  },

  loadSessions: async () => {
    // 检查是否有token，没有token则不发起请求
    const token = localStorage.getItem('token')
    if (!token) {
      set({ sessions: [] })
      return
    }
    
    try {
      const sessions = await sessionsApi.getSessions()
      set({ sessions })
    } catch (error: any) {
      // 如果是401错误，说明token无效，清空列表但不抛出错误
      if (error?.response?.status === 401) {
        set({ sessions: [] })
      } else {
        console.error('加载会话列表失败:', error)
      }
    }
  },

  loadMessages: async (sessionId: string) => {
    try {
      const messages = await sessionsApi.getSessionMessages(sessionId)
      set({ messages })
      return messages
    } catch (error) {
      console.error('加载消息失败:', error)
      return []
    }
  },

  addMessage: (message) => {
    set((state) => ({
      messages: [...state.messages, message],
    }))
  },

  updateMessage: (id, updates) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, ...updates } : msg
      ),
    }))
  },
}))

