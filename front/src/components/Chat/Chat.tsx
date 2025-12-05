import { useEffect, useRef } from 'react'
import Sidebar from './Sidebar'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { getWebSocketClient } from '../../services/websocket'
import { LLMMessage } from '../../types/websocket'

export default function Chat() {
  const { currentSession, messages, appendToLastAssistantMessage } = useChatStore()
  const { currentAgent, loadAgents } = useAgentStore()
  const unsubscribeRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    // 只在已登录时才加载数据
    const token = localStorage.getItem('token')
    if (token) {
      loadAgents()
    }
  }, [loadAgents])

  // 初始化 WebSocket 连接并监听 LLM 消息
  useEffect(() => {
    const wsClient = getWebSocketClient()
    
    // 确保 WebSocket 已连接
    const initWebSocket = async () => {
      try {
        if (!wsClient.isConnected()) {
          await wsClient.connect()
        }
      } catch (error) {
        console.error('WebSocket 连接失败:', error)
        return
      }
      
      // 监听 LLM 消息
      const unsubscribe = wsClient.onLLMMessage((llmMsg: LLMMessage) => {
        // 如果消息有内容，追加到最后一条 assistant 消息
        if (llmMsg.content !== undefined && llmMsg.content !== null && llmMsg.content !== '') {
          appendToLastAssistantMessage(llmMsg.content, llmMsg.finished || false)
        } 
        // 如果消息标记为完成，更新最后一条消息的状态
        else if (llmMsg.finished) {
          appendToLastAssistantMessage('', true)
        }
      })
      
      unsubscribeRef.current = unsubscribe
    }
    
    initWebSocket()
    
    // 清理函数
    return () => {
      if (unsubscribeRef.current) {
        unsubscribeRef.current()
        unsubscribeRef.current = null
      }
    }
  }, [appendToLastAssistantMessage])

  return (
    <div className="flex h-screen bg-gray-100">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        {currentAgent && (
          <div className="bg-white border-b border-gray-200 px-6 py-4">
            <h1 className="text-xl font-semibold">{currentAgent.name}</h1>
            {currentAgent.description && (
              <p className="text-sm text-gray-600 mt-1">{currentAgent.description}</p>
            )}
          </div>
        )}
        <MessageList messages={messages} />
        <ChatInput />
      </div>
    </div>
  )
}

