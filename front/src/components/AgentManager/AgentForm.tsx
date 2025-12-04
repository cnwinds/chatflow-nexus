import { useState, useEffect } from 'react'
import { useAgentStore } from '../../stores/agentStore'
import { agentsApi } from '../../services/agents'

interface AgentFormProps {
  agent?: any
  onClose: () => void
}

interface Template {
  id: number
  name: string
  description?: string
}

export default function AgentForm({ agent, onClose }: AgentFormProps) {
  const { createAgent, updateAgent } = useAgentStore()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [templateId, setTemplateId] = useState(1)
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingTemplates, setLoadingTemplates] = useState(false)

  useEffect(() => {
    if (agent) {
      setName(agent.name)
      setDescription(agent.description || '')
      setTemplateId(agent.template_id)
    }
  }, [agent])

  useEffect(() => {
    const loadTemplates = async () => {
      if (!agent) {
        setLoadingTemplates(true)
        try {
          const templateList = await agentsApi.getTemplates()
          setTemplates(templateList)
          if (templateList.length > 0) {
            setTemplateId(templateList[0].id)
          }
        } catch (error) {
          console.error('加载模板列表失败:', error)
        } finally {
          setLoadingTemplates(false)
        }
      }
    }
    loadTemplates()
  }, [agent])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      if (agent) {
        await updateAgent(agent.id, { name, description })
      } else {
        await createAgent({ name, description, template_id: templateId })
      }
      onClose()
    } catch (error) {
      alert('保存失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-md w-full">
        <h2 className="text-xl font-bold mb-4">
          {agent ? '编辑Agent' : '创建Agent'}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              名称
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              描述
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2"
              rows={3}
            />
          </div>
          {!agent && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                模板
              </label>
              {loadingTemplates ? (
                <div className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-500">
                  加载中...
                </div>
              ) : (
                <select
                  value={templateId}
                  onChange={(e) => setTemplateId(Number(e.target.value))}
                  required
                  className="w-full border border-gray-300 rounded-lg px-3 py-2"
                >
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}
          <div className="flex space-x-2">
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {loading ? '保存中...' : '保存'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400"
            >
              取消
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

