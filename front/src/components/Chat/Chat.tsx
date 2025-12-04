import { useState, useEffect, useRef } from 'react'
import Sidebar from './Sidebar'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'

export default function Chat() {
  const { currentSession, messages } = useChatStore()
  const { currentAgent, loadAgents } = useAgentStore()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // 只在已登录时才加载数据
    const token = localStorage.getItem('token')
    if (token) {
      loadAgents()
    }
  }, [loadAgents])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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

