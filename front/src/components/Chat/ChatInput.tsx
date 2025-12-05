import { useState, KeyboardEvent } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { sessionsApi } from '../../services/sessions'
import { getWebSocketClient } from '../../services/websocket'
import { TextMessage } from '../../types/websocket'

export default function ChatInput() {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const { currentSession, addMessage, setCurrentSession, messages, updateMessage } = useChatStore()
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

      // 创建一条空的assistant消息，标记为正在流式传输
      // 这样当收到 LLM 消息时，会自动追加到这条消息
      const assistantMessageId = Date.now() + 1
      addMessage({
        id: assistantMessageId,
        session_id: session.session_id,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
        isStreaming: true,
      })

      // 通过 WebSocket 直接发送文本消息
      try {
        const wsClient = getWebSocketClient()
        
        // 确保 WebSocket 已连接
        if (!wsClient.isConnected()) {
          await wsClient.connect()
        }
        
        // 发送文本消息
        const textMessage: TextMessage = {
          type: 'text',
          content: message,
          agent_id: agentId,
          session_id: session.session_id,
        }
        
        wsClient.sendText(textMessage)
        
        // 注意：LLM 响应会通过 Chat 组件中的全局监听器自动追加到消息中
        // 不需要在这里处理响应
      } catch (error) {
        // 发生错误时，标记消息为不再流式传输
        updateMessage(assistantMessageId, {
          isStreaming: false,
        })
        throw error
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

