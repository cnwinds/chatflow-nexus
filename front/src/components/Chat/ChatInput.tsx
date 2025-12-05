import { useState, KeyboardEvent, useEffect, useRef } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { sessionsApi } from '../../services/sessions'
import { getWebSocketClient } from '../../services/websocket'
import { TextMessage } from '../../types/websocket'
import { useVoiceInput } from '../../hooks/useVoiceInput'
import { MicrophoneIcon, StopIcon } from '@heroicons/react/24/solid'

export default function ChatInput() {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [inputMode, setInputMode] = useState<'text' | 'voice'>('text')
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

  // 当停止录音时，如果是在语音模式，自动切换到文本模式
  const prevIsRecordingRef = useRef(isRecording)
  useEffect(() => {
    if (prevIsRecordingRef.current && !isRecording && inputMode === 'voice') {
      // 录音已停止，可以切换回文本模式
      // 注意：语音识别结果会通过后端自动处理，不需要手动发送
    }
    prevIsRecordingRef.current = isRecording
  }, [isRecording, inputMode])

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

  const handleKeyPress = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleVoiceToggle = async () => {
    if (inputMode === 'text') {
      // 切换到语音模式
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
      
      setInputMode('voice')
      await startRecording()
    } else {
      // 切换回文本模式
      await stopRecording()
      setInputMode('text')
    }
  }

  const handleStopVoice = async () => {
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
    
    setInputMode('text')
  }

  return (
    <div className="border-t border-gray-200 bg-white p-4">
      <div className="flex items-end space-x-4">
        {inputMode === 'text' ? (
          <>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="输入消息... (Enter发送)"
              className="flex-1 resize-none border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              rows={1}
              disabled={loading}
            />
            {isSupported && (
              <button
                onClick={handleVoiceToggle}
                disabled={loading || !currentAgent}
                className="p-2 text-gray-600 hover:text-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title="切换到语音输入"
              >
                <MicrophoneIcon className="w-6 h-6" />
              </button>
            )}
            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '发送中...' : '发送'}
            </button>
          </>
        ) : (
          <>
            <div className="flex-1 flex items-center justify-center px-4 py-2 border border-gray-300 rounded-lg bg-gray-50">
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></div>
                <span className="text-gray-600">
                  {isRecording ? '正在录音...' : '准备录音...'}
                </span>
              </div>
            </div>
            <button
              onClick={handleStopVoice}
              className="p-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
              title="停止录音"
            >
              <StopIcon className="w-6 h-6" />
            </button>
            <button
              onClick={() => {
                setInputMode('text')
                stopRecording()
              }}
              className="px-4 py-2 text-gray-600 hover:text-gray-800 transition-colors"
            >
              取消
            </button>
          </>
        )}
      </div>
      {!isSupported && (
        <div className="mt-2 text-sm text-gray-500">
          您的浏览器不支持语音输入功能
        </div>
      )}
    </div>
  )
}

