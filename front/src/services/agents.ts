import api from './api'
import { Agent } from '../types'

export interface CreateAgentRequest {
  name: string
  description?: string
  template_id: number
  device_type?: number
  agent_config?: Record<string, any>
}

export interface UpdateAgentRequest {
  name?: string
  description?: string
  agent_config?: Record<string, any>
}

export const agentsApi = {
  getAgents: async () => {
    const response = await api.get<{ code: number; data: Agent[]; msg: string }>('/agents')
    if (response.code !== 0) {
      throw new Error(response.msg || '获取Agent列表失败')
    }
    return response.data || []
  },

  getAgent: async (agentId: number) => {
    const response = await api.get<{ code: number; data: Agent; msg: string }>(`/agents/${agentId}`)
    if (response.code !== 0) {
      throw new Error(response.msg || '获取Agent详情失败')
    }
    return response.data
  },

  createAgent: async (data: CreateAgentRequest) => {
    const response = await api.post<{ code: number; data: Agent; msg: string }>('/agents', data)
    if (response.code !== 0) {
      throw new Error(response.msg || '创建Agent失败')
    }
    return response.data
  },

  updateAgent: async (agentId: number, data: UpdateAgentRequest) => {
    const response = await api.put<{ code: number; data: Agent; msg: string }>(`/agents/${agentId}`, data)
    if (response.code !== 0) {
      throw new Error(response.msg || '更新Agent失败')
    }
    return response.data
  },

  deleteAgent: async (agentId: number) => {
    const response = await api.delete<{ code: number; msg: string }>(`/agents/${agentId}`)
    if (response.code !== 0) {
      throw new Error(response.msg || '删除Agent失败')
    }
    return response
  },

  getTemplates: async () => {
    const response = await api.get<{ code: number; data: Array<{ id: number; name: string; description?: string }>; msg: string }>('/agents/templates')
    if (response.code !== 0) {
      throw new Error(response.msg || '获取模板列表失败')
    }
    return response.data || []
  },
}

