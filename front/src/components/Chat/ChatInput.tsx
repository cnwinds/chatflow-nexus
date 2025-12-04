import { useState, KeyboardEvent } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { chatApi } from '../../services/chat'
import { sessionsApi } from '../../services/sessions'

export default function ChatInput() {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const { currentSession, addMessage, setCurrentSession, loadMessages } = useChatStore()
  const { currentAgent } = useAgentStore()

  const handleSend = async () => {
    if (!input.trim() || loading) return

    const message = input.trim()
    setInput('')
    setLoading(true)

    try {
      // 确保有会话和agent
      let session = currentSession
      let agentId = currentAgent?.id

      if (!session || !agentId) {
        if (!agentId) {
          alert('请先选择一个Agent')
          return
        }
        // 创建新会话
        session = await sessionsApi.createSession({ agent_id: agentId })
        setCurrentSession(session)
      }

      // 添加用户消息
      addMessage({
        id: Date.now(),
        session_id: session.session_id,
        role: 'user',
        content: message,
        created_at: new Date().toISOString(),
      })

      // 调用API
      let assistantMessage = ''
      const request = {
        model: `agent-${agentId}`,
        messages: [
          ...(await loadMessages(session.session_id)).map(m => ({
            role: m.role,
            content: m.content,
          })),
          { role: 'user' as const, content: message },
        ],
        stream: true,
        session_id: session.session_id,
      }

      // 流式接收响应
      for await (const chunk of chatApi.streamChatCompletion(request)) {
        const content = chunk.choices[0]?.delta?.content
        if (content) {
          assistantMessage += content
          // 更新最后一条消息
          addMessage({
            id: Date.now() + 1,
            session_id: session.session_id,
            role: 'assistant',
            content: assistantMessage,
            created_at: new Date().toISOString(),
          })
        }
      }
    } catch (error) {
      console.error('发送消息失败:', error)
      alert('发送消息失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="border-t border-gray-200 bg-white p-4">
      <div className="flex items-end space-x-4">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="输入消息... (Ctrl+Enter发送)"
          className="flex-1 resize-none border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          rows={1}
          disabled={loading}
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim()}
          className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? '发送中...' : '发送'}
        </button>
      </div>
    </div>
  )
}

