import { getWebSocketClient } from './websocket'
import { TextMessage, LLMMessage } from '../types/websocket'
import { ChatCompletionRequest, ChatCompletionChunk } from '../types'

// 提取agent_id从model字符串（格式：agent-{id}）
function extractAgentId(model: string): number | null {
  const match = model.match(/^agent-(\d+)$/)
  return match ? parseInt(match[1], 10) : null
}

// 互斥锁：确保一次只处理一个请求
let processingLock: Promise<void> | null = null
let currentRequestId: string | null = null

export const chatApi = {
  /**
   * 发送文本消息并接收流式响应
   * 注意：此方法使用WebSocket，需要先确保WebSocket已连接
   * 使用队列机制确保一次只处理一个请求
   */
  streamChatCompletion: async function* (
    request: ChatCompletionRequest
  ): AsyncGenerator<ChatCompletionChunk, void, unknown> {
    const wsClient = getWebSocketClient()
    
    // 确保WebSocket已连接
    if (!wsClient.isConnected()) {
      await wsClient.connect()
    }
    
    // 提取agent_id
    const agentId = extractAgentId(request.model)
    if (!agentId) {
      throw new Error(`无效的model格式: ${request.model}，应为 agent-{id}`)
    }
    
    // 提取最后一条用户消息
    const userMessages = request.messages.filter(msg => {
      const role = typeof msg === 'object' && 'role' in msg ? msg.role : msg
      return role === 'user'
    })
    
    if (userMessages.length === 0) {
      throw new Error('消息列表中必须包含至少一条用户消息')
    }
    
    const lastUserMessage = userMessages[userMessages.length - 1]
    const content = typeof lastUserMessage === 'object' && 'content' in lastUserMessage
      ? lastUserMessage.content
      : String(lastUserMessage)
    
    // 生成请求ID
    const requestId = `req-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    
    // 等待之前的请求完成
    if (processingLock) {
      await processingLock
    }
    
    // 创建处理锁
    let resolveLock: () => void
    processingLock = new Promise<void>((resolve) => {
      resolveLock = resolve
    })
    currentRequestId = requestId
    
    // 创建文本消息
    const textMessage: TextMessage = {
      type: 'text',
      content: content,
      agent_id: agentId,
      session_id: request.session_id,
    }
    
    // 设置当前请求状态
    let fullContent = ''
    let lastSentLength = 0
    let finished = false
    let error: Error | null = null
    let hasNewContent = false
    
    // 注册LLM消息回调（只处理当前请求的消息）
    const unsubscribe = wsClient.onLLMMessage((llmMsg: LLMMessage) => {
      // 只处理当前请求的消息
      if (currentRequestId !== requestId) {
        return
      }
      if (llmMsg.content !== undefined && llmMsg.content !== null) {
        fullContent += llmMsg.content
        hasNewContent = true
      }
      if (llmMsg.finished) {
        finished = true
      }
    })
    
    // 也监听错误
    const errorUnsubscribe = wsClient.onError((errorMsg) => {
      // 只处理当前请求的错误
      if (currentRequestId !== requestId) {
        return
      }
      error = new Error(errorMsg.message)
      finished = true
    })
    
    try {
      // 发送文本消息
      wsClient.sendText(textMessage)
      
      // 流式返回响应
      const responseId = `chatcmpl-${Date.now()}`
      const created = Math.floor(Date.now() / 1000)
      const maxWaitTime = 30000 // 30秒超时
      const startTime = Date.now()
      
      while (!finished && !error) {
        // 等待新内容或完成信号
        await new Promise(resolve => setTimeout(resolve, 50))
        
        // 检查超时
        if (Date.now() - startTime > maxWaitTime) {
          error = new Error('响应超时')
          break
        }
        
        // 如果有新内容，发送增量
        if (hasNewContent && fullContent.length > lastSentLength) {
          const newContent = fullContent.slice(lastSentLength)
          lastSentLength = fullContent.length
          hasNewContent = false
          
          const chunk: ChatCompletionChunk = {
            id: responseId,
            object: 'chat.completion.chunk',
            created: created,
            model: request.model,
            choices: [{
              index: 0,
              delta: {
                role: 'assistant',
                content: newContent,
              },
              finish_reason: null,
            }],
          }
          
          yield chunk
        }
      }
      
      // 如果有错误，抛出
      if (error) {
        throw error
      }
      
      // 发送最终chunk
      const finalChunk: ChatCompletionChunk = {
        id: responseId,
        object: 'chat.completion.chunk',
        created: created,
        model: request.model,
        choices: [{
          index: 0,
          delta: {},
          finish_reason: 'stop',
        }],
      }
      
      yield finalChunk
      
    } finally {
      unsubscribe()
      errorUnsubscribe()
      // 释放锁
      if (currentRequestId === requestId) {
        currentRequestId = null
      }
      if (processingLock && resolveLock!) {
        resolveLock()
        processingLock = null
      }
    }
  },
  
  /**
   * 非流式聊天完成（已废弃，建议使用streamChatCompletion）
   * 保留用于兼容性
   */
  chatCompletion: async (request: ChatCompletionRequest): Promise<Response> => {
    throw new Error('chatCompletion已废弃，请使用streamChatCompletion')
  },
}
