import { useState, KeyboardEvent, useEffect, useRef } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { sessionsApi } from '../../services/sessions'
import { getWebSocketClient } from '../../services/websocket'
import { TextMessage } from '../../types/websocket'
import { useVoiceInput } from '../../hooks/useVoiceInput'
import { 
  MicrophoneIcon, 
  PaperAirplaneIcon,
  PauseIcon,
  XMarkIcon
} from '@heroicons/react/24/solid'

export default function ChatInput() {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { currentSession, addMessage, setCurrentSession, messages, updateMessage, addSession } = useChatStore()
  const { currentAgent } = useAgentStore()
  
  // 语音输入
  const {
    isRecording,
    isSupported,
    startRecording,
    stopRecording,
    checkSupport,
  } = useVoiceInput({
    sessionId: currentSession?.session_id,
    agentId: currentAgent?.id,
    onError: (error) => {
      console.error('语音输入错误:', error)
      alert(`语音输入错误: ${error.message}`)
    },
  })

  // 检查浏览器支持
  useEffect(() => {
    checkSupport()
  }, [checkSupport])

  // 自动调整文本输入框高度
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [input])

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
        addSession(session)
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

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Ctrl+Enter 或 Cmd+Enter 发送消息
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSend()
    }
    // 普通 Enter 键默认行为是换行，不需要阻止
  }

  const handleVoiceStart = async () => {
    if (!currentAgent?.id) {
      alert('请先选择一个Agent')
      return
    }
    
    // 确保有会话
    let session = currentSession
    if (!session) {
      session = await sessionsApi.createSession({ agent_id: currentAgent.id })
      setCurrentSession(session)
      addSession(session)
    }
    
    // 确保 WebSocket 已连接
    const wsClient = getWebSocketClient()
    if (!wsClient.isConnected()) {
      await wsClient.connect()
    }
    
    await startRecording()
  }

  const handleVoiceStop = async () => {
    await stopRecording()
    
    // 确保有会话和agent
    if (currentSession && currentAgent) {
      // 创建一条空的assistant消息，等待LLM响应
      // 语音识别结果会通过后端自动处理并触发LLM响应
      const assistantMessageId = Date.now() + 1
      addMessage({
        id: assistantMessageId,
        session_id: currentSession.session_id,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
        isStreaming: true,
      })
    }
  }

  return (
    <div className="border-t border-border-primary bg-bg-primary">
      {/* 录音状态栏 */}
      {isRecording && (
        <div className="px-4 py-2 bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-800 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="relative">
              <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></div>
              <div className="absolute inset-0 w-3 h-3 bg-red-500 rounded-full animate-ping opacity-75"></div>
            </div>
            <span className="text-sm font-medium text-red-700 dark:text-red-400">
              正在录音中...
            </span>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={handleVoiceStop}
              className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-md text-sm font-medium transition-colors flex items-center space-x-1"
            >
              <PauseIcon className="w-4 h-4" />
              <span>停止</span>
            </button>
          </div>
        </div>
      )}

      {/* 输入区域 */}
      <div className="p-4">
        <div className="flex items-center space-x-3">
          {/* 文本输入框 */}
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isRecording ? "正在录音，您也可以继续输入文字..." : "输入消息... (Ctrl+Enter发送)"}
              className="w-full resize-none border border-border-primary rounded-xl px-4 py-3 pr-12 bg-bg-primary text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-all min-h-[52px] max-h-[200px] overflow-y-auto"
              rows={1}
              disabled={loading}
            />
            {/* 输入框内的快捷提示 */}
            {!input && !isRecording && (
              <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none">
                <span className="text-xs text-text-tertiary">Ctrl+Enter 发送</span>
              </div>
            )}
          </div>

          {/* 操作按钮组 */}
          <div className="flex items-center space-x-2">
            {/* 语音按钮 */}
            {isSupported && (
              <button
                onClick={isRecording ? handleVoiceStop : handleVoiceStart}
                disabled={loading || !currentAgent}
                className={`flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center transition-all ${
                  isRecording
                    ? 'bg-red-500 hover:bg-red-600 text-white animate-pulse'
                    : 'bg-bg-secondary hover:bg-bg-hover text-text-secondary hover:text-accent-primary'
                } disabled:opacity-50 disabled:cursor-not-allowed`}
                title={isRecording ? '停止录音' : '开始语音输入'}
              >
                {isRecording ? (
                  <PauseIcon className="w-6 h-6" />
                ) : (
                  <MicrophoneIcon className="w-6 h-6" />
                )}
              </button>
            )}

            {/* 发送按钮 */}
            <button
              onClick={handleSend}
              disabled={loading || (!input.trim() && !isRecording)}
              className="flex-shrink-0 w-12 h-12 bg-accent-primary hover:bg-accent-hover text-text-inverse rounded-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center"
              title="发送消息 (Ctrl+Enter)"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              ) : (
                <PaperAirplaneIcon className="w-6 h-6" />
              )}
            </button>
          </div>
        </div>

        {/* 底部提示信息 */}
        <div className="mt-2 flex items-center justify-between text-xs">
          <div className="flex items-center space-x-4 text-text-tertiary">
            {isSupported ? (
              <span className="flex items-center space-x-1">
                <MicrophoneIcon className="w-3 h-3" />
                <span>支持语音输入</span>
              </span>
            ) : (
              <span className="text-text-tertiary">您的浏览器不支持语音输入</span>
            )}
          </div>
          {input && (
            <span className="text-text-tertiary">
              {input.length} 字符
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

