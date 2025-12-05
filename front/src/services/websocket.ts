import {
  WebSocketMessage,
  HelloRequest,
  HelloResponse,
  TextMessage,
  LLMMessage,
  TTSMessage,
  ErrorMessage,
  WebSocketState,
} from '../types/websocket'

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8020'

// 生成并存储Client-Id
function getOrCreateClientId(): string {
  const STORAGE_KEY = 'websocket_client_id'
  let clientId = localStorage.getItem(STORAGE_KEY)
  
  if (!clientId) {
    // 生成UUID v4
    clientId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0
      const v = c === 'x' ? r : (r & 0x3) | 0x8
      return v.toString(16)
    })
    localStorage.setItem(STORAGE_KEY, clientId)
  }
  
  return clientId
}

export class WebSocketClient {
  private ws: WebSocket | null = null
  private state: WebSocketState = WebSocketState.DISCONNECTED
  private clientId: string
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000
  private reconnectTimer: number | null = null
  private helloExchanged = false
  
  // 事件回调
  private onStateChangeCallbacks: Array<(state: WebSocketState) => void> = []
  private onLLMMessageCallbacks: Array<(message: LLMMessage) => void> = []
  private onTTSMessageCallbacks: Array<(message: TTSMessage) => void> = []
  private onErrorCallbacks: Array<(error: ErrorMessage) => void> = []
  private onBinaryCallbacks: Array<(data: ArrayBuffer) => void> = []
  
  constructor() {
    this.clientId = getOrCreateClientId()
  }
  
  // 状态管理
  getState(): WebSocketState {
    return this.state
  }
  
  isConnected(): boolean {
    return this.state === WebSocketState.CONNECTED && this.helloExchanged
  }
  
  private setState(newState: WebSocketState) {
    if (this.state !== newState) {
      this.state = newState
      this.onStateChangeCallbacks.forEach(callback => callback(newState))
    }
  }
  
  // 事件监听
  onStateChange(callback: (state: WebSocketState) => void) {
    this.onStateChangeCallbacks.push(callback)
    return () => {
      const index = this.onStateChangeCallbacks.indexOf(callback)
      if (index > -1) {
        this.onStateChangeCallbacks.splice(index, 1)
      }
    }
  }
  
  onLLMMessage(callback: (message: LLMMessage) => void) {
    this.onLLMMessageCallbacks.push(callback)
    return () => {
      const index = this.onLLMMessageCallbacks.indexOf(callback)
      if (index > -1) {
        this.onLLMMessageCallbacks.splice(index, 1)
      }
    }
  }
  
  onTTSMessage(callback: (message: TTSMessage) => void) {
    this.onTTSMessageCallbacks.push(callback)
    return () => {
      const index = this.onTTSMessageCallbacks.indexOf(callback)
      if (index > -1) {
        this.onTTSMessageCallbacks.splice(index, 1)
      }
    }
  }
  
  onError(callback: (error: ErrorMessage) => void) {
    this.onErrorCallbacks.push(callback)
    return () => {
      const index = this.onErrorCallbacks.indexOf(callback)
      if (index > -1) {
        this.onErrorCallbacks.splice(index, 1)
      }
    }
  }
  
  onBinary(callback: (data: ArrayBuffer) => void) {
    this.onBinaryCallbacks.push(callback)
    return () => {
      const index = this.onBinaryCallbacks.indexOf(callback)
      if (index > -1) {
        this.onBinaryCallbacks.splice(index, 1)
      }
    }
  }
  
  // 连接管理
  async connect(): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN && this.helloExchanged) {
      return
    }
    
    return new Promise((resolve, reject) => {
      let helloResolve: (() => void) | null = null
      let helloReject: ((error: Error) => void) | null = null
      const helloPromise = new Promise<void>((res, rej) => {
        helloResolve = res
        helloReject = rej
      })
      
      // 设置hello超时
      const helloTimeout = setTimeout(() => {
        if (helloReject) {
          helloReject(new Error('Hello消息交换超时'))
        }
      }, 5000)
      try {
        const token = localStorage.getItem('token')
        if (!token) {
          reject(new Error('未找到token，请先登录'))
          return
        }
        
        this.setState(WebSocketState.CONNECTING)
        
        // 构建WebSocket URL（通过URL参数传递认证信息）
        const url = new URL(`${WS_BASE_URL}/ws/chat`)
        url.searchParams.set('token', token)
        url.searchParams.set('protocol_version', '1')
        url.searchParams.set('client_id', this.clientId)
        
        // 创建WebSocket连接
        this.ws = new WebSocket(url.toString())
        
        // 设置headers（通过URL参数或子协议，但浏览器WebSocket API不支持自定义headers）
        // 我们需要在连接建立后通过第一个消息发送认证信息
        // 但根据协议，我们需要在连接时发送headers，所以这里先连接，认证在hello消息中处理
        
        // 注意：浏览器WebSocket API不支持在连接时设置自定义headers
        // 我们需要修改后端，允许通过URL参数或第一个消息进行认证
        // 或者使用wscat等工具测试时可以通过headers
        
        // 临时方案：在连接建立后立即发送认证信息（如果后端支持）
        // 或者修改后端支持通过URL参数传递token
        
        this.ws.onopen = () => {
          console.log('WebSocket连接已打开，准备发送Hello消息')
          this.setState(WebSocketState.CONNECTED)
          this.reconnectAttempts = 0
          
          // 发送hello消息
          this.sendHello()
            .then(() => {
              console.log('Hello消息已发送，等待响应...')
            })
            .catch(err => {
              console.error('发送Hello消息失败:', err)
              if (helloReject) {
                helloReject(err)
              }
            })
        }
        
        // 保存原始的handleMessage
        const originalHandleMessage = this.handleMessage.bind(this)
        
        // 创建一个标志来跟踪是否已经resolve了hello
        let helloResolved = false
        
        this.ws.onmessage = (event) => {
          // 先检查是否是hello响应（在handleMessage之前）
          try {
            const message = JSON.parse(event.data)
            if (message.type === 'hello' && !helloResolved) {
              this.helloExchanged = true
              helloResolved = true
              clearTimeout(helloTimeout)
              if (helloResolve) {
                console.log('Hello消息交换完成，调用resolve')
                helloResolve()
              }
            }
          } catch {
            // 不是JSON消息，继续处理
          }
          
          // 然后调用原始的消息处理器
          originalHandleMessage(event)
        }
        
        this.ws.onerror = (error) => {
          console.error('WebSocket错误:', error)
          this.setState(WebSocketState.ERROR)
          clearTimeout(helloTimeout)
          if (helloReject) {
            helloReject(new Error('WebSocket连接错误'))
          }
          reject(error)
        }
        
        this.ws.onclose = (event) => {
          this.setState(WebSocketState.DISCONNECTED)
          this.helloExchanged = false
          clearTimeout(helloTimeout)
          
          // 如果hello还没有完成，reject promise
          if (!helloResolved && helloReject) {
            helloReject(new Error('WebSocket连接关闭，Hello消息交换未完成'))
          }
          
          // 如果不是主动关闭，尝试重连
          if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect()
          }
        }
        
        // 等待hello交换完成
        helloPromise
          .then(() => {
            resolve()
          })
          .catch((err) => {
            reject(err)
          })
        
      } catch (error) {
        this.setState(WebSocketState.ERROR)
        clearTimeout(helloTimeout)
        reject(error)
      }
    })
  }
  
  private scheduleReconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
    }
    
    this.reconnectAttempts++
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1)
    
    this.reconnectTimer = window.setTimeout(() => {
      console.log(`尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`)
      this.connect().catch(() => {
        // 重连失败，继续尝试
      })
    }, delay)
  }
  
  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    
    if (this.ws) {
      this.ws.close(1000, '正常关闭')
      this.ws = null
    }
    
    this.setState(WebSocketState.DISCONNECTED)
    this.helloExchanged = false
  }
  
  // 消息处理
  private handleMessage(event: MessageEvent) {
    if (event.data instanceof ArrayBuffer) {
      // 二进制消息（音频数据）
      this.onBinaryCallbacks.forEach(callback => callback(event.data))
      return
    }
    
    try {
      const message: WebSocketMessage = JSON.parse(event.data)
      
      switch (message.type) {
        case 'hello':
          // Hello响应（helloExchanged标志在connect的onmessage中设置）
          console.log('收到Hello响应:', message)
          // 确保标志已设置（防止在connect之外收到hello消息）
          if (!this.helloExchanged) {
            this.helloExchanged = true
          }
          break
          
        case 'llm':
          console.log('收到LLM消息:', message)
          this.onLLMMessageCallbacks.forEach(callback => callback(message as LLMMessage))
          break
          
        case 'tts':
          console.log('收到TTS消息:', message)
          this.onTTSMessageCallbacks.forEach(callback => callback(message as TTSMessage))
          break
          
        case 'error':
          console.error('收到错误消息:', message)
          this.onErrorCallbacks.forEach(callback => callback(message as ErrorMessage))
          break
          
        default:
          console.warn('未知的WebSocket消息类型:', message)
      }
    } catch (error) {
      console.error('解析WebSocket消息失败:', error)
    }
  }
  
  // 发送消息
  private send(message: WebSocketMessage | string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket未连接')
    }
    
    const data = typeof message === 'string' ? message : JSON.stringify(message)
    this.ws.send(data)
  }
  
  async sendHello(): Promise<void> {
    const hello: HelloRequest = {
      type: 'hello',
      version: 1,
      transport: 'websocket',
      features: {
        mcp: true,
      },
      audio_params: {
        format: 'opus',
        sample_rate: 16000,
        channels: 1,
        frame_duration: 60,
      },
    }
    
    this.send(hello)
  }
  
  sendText(message: TextMessage): void {
    console.log('WebSocket发送文本消息:', message)
    this.send(message)
  }
  
  sendBinary(data: ArrayBuffer | Uint8Array): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket未连接')
    }
    
    this.ws.send(data)
  }
}

// 单例实例
let wsClientInstance: WebSocketClient | null = null

export function getWebSocketClient(): WebSocketClient {
  if (!wsClientInstance) {
    wsClientInstance = new WebSocketClient()
  }
  return wsClientInstance
}

