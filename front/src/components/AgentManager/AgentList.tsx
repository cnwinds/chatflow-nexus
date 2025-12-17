import { useState } from 'react'
import { useAgentStore } from '../../stores/agentStore'
import AgentForm from './AgentForm'

export default function AgentList() {
  const { agents, deleteAgent } = useAgentStore()
  const [showForm, setShowForm] = useState(false)
  const [editingAgent, setEditingAgent] = useState<any>(null)

  const handleDelete = async (id: number) => {
    if (confirm('确定要删除这个Agent吗？')) {
      try {
        await deleteAgent(id)
      } catch (error) {
        alert('删除失败')
      }
    }
  }

  return (
    <div>
      <div className="mb-4">
        <button
          onClick={() => {
            setEditingAgent(null)
            setShowForm(true)
          }}
          className="px-4 py-2 bg-accent-primary hover:bg-accent-hover text-text-inverse rounded-lg transition-colors"
        >
          + 创建Agent
        </button>
      </div>

      {showForm && (
        <AgentForm
          agent={editingAgent}
          onClose={() => {
            setShowForm(false)
            setEditingAgent(null)
          }}
        />
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className="bg-bg-primary rounded-lg shadow border border-border-primary p-6 hover:shadow-lg transition-shadow"
          >
            <h3 className="text-lg font-semibold mb-2 text-text-primary">{agent.name}</h3>
            {agent.description && (
              <p className="text-text-secondary text-sm mb-4">{agent.description}</p>
            )}
            <div className="flex space-x-2">
              <button
                onClick={() => {
                  setEditingAgent(agent)
                  setShowForm(true)
                }}
                className="flex-1 px-3 py-2 bg-accent-primary hover:bg-accent-hover text-text-inverse rounded text-sm transition-colors"
              >
                编辑
              </button>
              <button
                onClick={() => handleDelete(agent.id)}
                className="flex-1 px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm transition-colors"
              >
                删除
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

