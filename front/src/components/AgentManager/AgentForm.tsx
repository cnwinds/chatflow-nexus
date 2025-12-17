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
    <div className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-center justify-center z-50">
      <div className="bg-bg-primary rounded-lg p-6 max-w-md w-full border border-border-primary shadow-lg">
        <h2 className="text-xl font-bold mb-4 text-text-primary">
          {agent ? '编辑Agent' : '创建Agent'}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">
              名称
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full border border-border-primary bg-bg-primary text-text-primary rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent-primary transition-colors"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">
              描述
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full border border-border-primary bg-bg-primary text-text-primary rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent-primary transition-colors"
              rows={3}
            />
          </div>
          {!agent && (
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1">
                模板
              </label>
              {loadingTemplates ? (
                <div className="w-full border border-border-primary rounded-lg px-3 py-2 text-text-tertiary bg-bg-secondary">
                  加载中...
                </div>
              ) : (
                <select
                  value={templateId}
                  onChange={(e) => setTemplateId(Number(e.target.value))}
                  required
                  className="w-full border border-border-primary bg-bg-primary text-text-primary rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent-primary transition-colors"
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
              className="flex-1 px-4 py-2 bg-accent-primary hover:bg-accent-hover text-text-inverse rounded-lg disabled:opacity-50 transition-colors"
            >
              {loading ? '保存中...' : '保存'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-bg-tertiary hover:bg-bg-hover text-text-primary rounded-lg transition-colors"
            >
              取消
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

