import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { sessionsApi } from '../../services/sessions'
import ThemeToggle from '../ThemeToggle'

export default function Sidebar() {
  const { user, logout } = useAuthStore()
  const { currentSession, setCurrentSession, sessions, loadSessions, addSession } = useChatStore()
  const { currentAgent, setCurrentAgent, agents, loadAgents } = useAgentStore()
  const navigate = useNavigate()
  const [showAgentSelector, setShowAgentSelector] = useState(false)

  useEffect(() => {
    // 只在已登录时才加载数据
    const token = localStorage.getItem('token')
    if (token) {
      loadSessions()
      loadAgents()
    }
  }, [loadSessions, loadAgents])

  const handleNewChat = async () => {
    if (!currentAgent) {
      setShowAgentSelector(true)
      return
    }
    // 创建新会话的逻辑在ChatInput中处理
  }

  const handleSelectAgent = async (agentId: number) => {
    try {
      const session = await sessionsApi.createSession({ agent_id: agentId })
      setCurrentSession(session)
      addSession(session)
      setCurrentAgent(agents.find(a => a.id === agentId) || null)
      setShowAgentSelector(false)
    } catch (error) {
      console.error('创建会话失败:', error)
    }
  }

  return (
    <div className="w-64 bg-bg-tertiary text-text-primary flex flex-col">
      <div className="p-4 border-b border-border-primary flex items-center justify-between">
        <button
          onClick={handleNewChat}
          className="flex-1 bg-accent-primary hover:bg-accent-hover px-4 py-2 rounded-md text-sm font-medium text-text-inverse transition-colors"
        >
          + 新对话
        </button>
        <div className="ml-2">
          <ThemeToggle />
        </div>
      </div>

      {showAgentSelector && (
        <div className="p-4 border-b border-border-primary">
          <h3 className="text-sm font-medium mb-2 text-text-primary">选择Agent</h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {agents.map((agent) => (
              <button
                key={agent.id}
                onClick={() => handleSelectAgent(agent.id)}
                className="w-full text-left px-3 py-2 rounded hover:bg-bg-hover text-sm text-text-primary transition-colors"
              >
                {agent.name}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-2">
        <div className="space-y-1">
          {sessions.map((session) => (
            <button
              key={session.session_id}
              onClick={async () => {
                setCurrentSession(session)
                const agent = agents.find(a => a.id === session.agent_id)
                if (agent) {
                  setCurrentAgent(agent)
                }
              }}
              className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${
                currentSession?.session_id === session.session_id
                  ? 'bg-bg-active text-text-primary'
                  : 'hover:bg-bg-hover text-text-primary'
              }`}
            >
              <div className="truncate">{session.title || '新对话'}</div>
              <div className="text-xs text-text-tertiary mt-1">
                {new Date(session.updated_at).toLocaleDateString()}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 border-t border-border-primary">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-text-primary">{user?.user_name}</span>
          <button
            onClick={() => navigate('/agents')}
            className="text-sm text-accent-primary hover:text-accent-hover transition-colors"
          >
            管理Agent
          </button>
        </div>
        <button
          onClick={logout}
          className="w-full text-left text-sm text-text-secondary hover:text-text-primary transition-colors"
        >
          退出登录
        </button>
      </div>
    </div>
  )
}

