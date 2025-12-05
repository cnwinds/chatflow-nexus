import { create } from 'zustand'
import { Session, Message } from '../types'
import { sessionsApi } from '../services/sessions'

interface ChatState {
  currentSession: Session | null
  sessions: Session[]
  messages: Message[]
  setCurrentSession: (session: Session | null) => void
  loadSessions: () => Promise<void>
  addSession: (session: Session) => void
  loadMessages: (sessionId: string) => Promise<Message[]>
  addMessage: (message: Message) => void
  updateMessage: (id: number, updates: Partial<Message>) => void
  appendToLastAssistantMessage: (content: string, finished?: boolean) => void
  getOrCreateStreamingAssistantMessage: (sessionId: string) => number
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

  addSession: (session) => {
    set((state) => {
      // 检查会话是否已存在，避免重复添加
      const exists = state.sessions.some(s => s.session_id === session.session_id)
      if (exists) {
        return state
      }
      // 将新会话添加到列表开头
      return { sessions: [session, ...state.sessions] }
    })
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

  // 追加内容到最后一条 assistant 消息（如果存在且正在流式传输），否则创建新消息
  appendToLastAssistantMessage: (content, finished = false) => {
    set((state) => {
      const messages = [...state.messages]
      const lastMessage = messages[messages.length - 1]
      
      // 如果最后一条消息是 assistant 且正在流式传输，追加内容或更新状态
      if (lastMessage && lastMessage.role === 'assistant') {
        const updatedMessage = {
          ...lastMessage,
          content: content ? (lastMessage.content || '') + content : lastMessage.content,
          isStreaming: !finished,
        }
        messages[messages.length - 1] = updatedMessage
        return { messages }
      } else if (content) {
        // 否则创建新的 assistant 消息（只有当有内容时才创建）
        const newMessage: Message = {
          id: Date.now(),
          session_id: state.currentSession?.session_id || '',
          role: 'assistant',
          content: content,
          created_at: new Date().toISOString(),
          isStreaming: !finished,
        }
        return { messages: [...messages, newMessage] }
      }
      
      // 如果既没有最后一条 assistant 消息，也没有内容，不做任何操作
      return { messages }
    })
  },

  // 获取或创建一条正在流式传输的 assistant 消息
  getOrCreateStreamingAssistantMessage: (sessionId) => {
    const state = useChatStore.getState()
    const messages = state.messages
    const lastMessage = messages[messages.length - 1]
    
    // 如果最后一条消息是 assistant 且正在流式传输，返回其 ID
    if (lastMessage && lastMessage.role === 'assistant' && lastMessage.isStreaming) {
      return lastMessage.id
    }
    
    // 否则创建新的 assistant 消息
    const newMessage: Message = {
      id: Date.now(),
      session_id: sessionId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      isStreaming: true,
    }
    state.addMessage(newMessage)
    return newMessage.id
  },
}))

