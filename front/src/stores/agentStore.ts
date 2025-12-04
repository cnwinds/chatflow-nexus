import { create } from 'zustand'
import { Agent } from '../types'
import { agentsApi } from '../services/agents'

interface AgentState {
  agents: Agent[]
  currentAgent: Agent | null
  loadAgents: () => Promise<void>
  setCurrentAgent: (agent: Agent | null) => void
  createAgent: (data: any) => Promise<void>
  updateAgent: (id: number, data: any) => Promise<void>
  deleteAgent: (id: number) => Promise<void>
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: [],
  currentAgent: null,

  loadAgents: async () => {
    // 检查是否有token，没有token则不发起请求
    const token = localStorage.getItem('token')
    if (!token) {
      set({ agents: [] })
      return
    }
    
    try {
      const agents = await agentsApi.getAgents()
      set({ agents })
    } catch (error: any) {
      // 如果是401错误，说明token无效，清空列表但不抛出错误
      if (error?.response?.status === 401) {
        set({ agents: [] })
      } else {
        console.error('加载Agent列表失败:', error)
      }
    }
  },

  setCurrentAgent: (agent) => {
    set({ currentAgent: agent })
  },

  createAgent: async (data) => {
    try {
      await agentsApi.createAgent(data)
      // 重新加载列表
      const agents = await agentsApi.getAgents()
      set({ agents })
    } catch (error) {
      console.error('创建Agent失败:', error)
      throw error
    }
  },

  updateAgent: async (id, data) => {
    try {
      await agentsApi.updateAgent(id, data)
      // 重新加载列表
      const agents = await agentsApi.getAgents()
      set({ agents })
    } catch (error) {
      console.error('更新Agent失败:', error)
      throw error
    }
  },

  deleteAgent: async (id) => {
    try {
      await agentsApi.deleteAgent(id)
      // 重新加载列表
      const agents = await agentsApi.getAgents()
      set({ agents })
    } catch (error) {
      console.error('删除Agent失败:', error)
      throw error
    }
  },
}))

