// WebSocket消息类型定义

export interface AudioParams {
  format: string
  sample_rate: number
  channels: number
  frame_duration: number
}

// Hello消息
export interface HelloRequest {
  type: 'hello'
  version: number
  transport: string
  features?: {
    mcp?: boolean
  }
  audio_params?: AudioParams
}

export interface HelloResponse {
  type: 'hello'
  transport: string
  audio_params?: AudioParams
}

// Listen消息
export interface ListenMessage {
  session_id?: string
  type: 'listen'
  state: 'start' | 'stop' | 'detect'
  mode?: 'auto' | 'manual' | 'realtime'
  text?: string
  agent_id?: number
}

// Text消息
export interface TextMessage {
  session_id?: string
  type: 'text'
  content: string
  agent_id?: number
}

// TTS消息（服务端发送）
export interface TTSMessage {
  type: 'tts'
  state: 'start' | 'stop' | 'sentence_start'
  text?: string
}

// LLM消息（服务端发送）
export interface LLMMessage {
  type: 'llm'
  content?: string
  emotion?: string
  finished?: boolean
}

// Abort消息
export interface AbortMessage {
  session_id?: string
  type: 'abort'
  reason?: string
}

// MCP消息
export interface MCPMessage {
  session_id?: string
  type: 'mcp'
  payload: Record<string, any>
}

// Error消息（服务端发送）
export interface ErrorMessage {
  type: 'error'
  code: number
  message: string
  details?: Record<string, any>
}

// 所有消息类型的联合
export type WebSocketMessage =
  | HelloRequest
  | HelloResponse
  | ListenMessage
  | TextMessage
  | TTSMessage
  | LLMMessage
  | AbortMessage
  | MCPMessage
  | ErrorMessage

// WebSocket连接状态
export enum WebSocketState {
  DISCONNECTED = 'disconnected',
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  ERROR = 'error',
}

