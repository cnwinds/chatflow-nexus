import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAgentStore } from '../../stores/agentStore'
import AgentList from './AgentList'

export default function AgentManager() {
  const { loadAgents } = useAgentStore()
  const navigate = useNavigate()

  useEffect(() => {
    // 只在已登录时才加载数据
    const token = localStorage.getItem('token')
    if (token) {
      loadAgents()
    }
  }, [loadAgents])

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Agent管理</h1>
          <button
            onClick={() => navigate('/')}
            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700"
          >
            返回聊天
          </button>
        </div>
        <AgentList />
      </div>
    </div>
  )
}

