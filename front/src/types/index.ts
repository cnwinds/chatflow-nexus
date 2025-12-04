export interface User {
  id: number
  user_name: string
  login_name: string
  mobile?: string
  avatar?: string
}

export interface Agent {
  id: number
  name: string
  description?: string
  avatar?: string
  gender: number
  device_type: number
  template_id: number
  template_name?: string
  agent_config: Record<string, any>
  status: number
  created_at: string
  updated_at?: string
}

export interface Session {
  session_id: string
  user_id: number
  agent_id: number
  agent_name: string
  title?: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface Message {
  id: number
  session_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
}

export interface ChatCompletionRequest {
  model: string
  messages: Array<{
    role: 'user' | 'assistant' | 'system'
    content: string
  }>
  stream?: boolean
  session_id?: string
}

export interface ChatCompletionChunk {
  id: string
  object: string
  created: number
  model: string
  choices: Array<{
    index: number
    delta: {
      role?: string
      content?: string
    }
    finish_reason?: string | null
  }>
}

