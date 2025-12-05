import { useRef, useLayoutEffect } from 'react'
import { Message } from '../../types'
import MessageItem from './MessageItem'

interface MessageListProps {
  messages: Message[]
}

export default function MessageList({ messages }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const prevMessagesLengthRef = useRef<number>(0)
  const prevFirstMessageIdRef = useRef<number | undefined>(undefined)
  const prevLastMessageContentRef = useRef<string>('')
  const prevLastMessageIdRef = useRef<number | undefined>(undefined)

  // 滚动到底部的函数
  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior })
    }
  }

  // 使用 useLayoutEffect 在 DOM 更新后立即滚动（更及时）
  useLayoutEffect(() => {
    if (messages.length > 0) {
      const firstMessageId = messages[0]?.id
      const lastMessage = messages[messages.length - 1]
      const lastMessageId = lastMessage?.id
      const lastMessageContent = lastMessage?.content || ''
      
      const isNewSession = prevFirstMessageIdRef.current !== undefined && 
                           prevFirstMessageIdRef.current !== firstMessageId
      const isInitialLoad = prevMessagesLengthRef.current === 0 && messages.length > 0
      const isNewMessage = messages.length > prevMessagesLengthRef.current
      // 检测最后一条消息的内容是否更新（流式更新）
      const isContentUpdated = lastMessageId === prevLastMessageIdRef.current &&
                               lastMessageContent !== prevLastMessageContentRef.current
      // 检测是否是同一条消息但内容在更新（流式传输中）
      const isStreamingUpdate = isContentUpdated && lastMessage?.isStreaming
      
      // 如果是新会话、首次加载、新消息或流式更新，滚动到底部
      if (isNewSession || isInitialLoad || isNewMessage || isStreamingUpdate) {
        // 使用 requestAnimationFrame 确保在浏览器重绘前执行
        requestAnimationFrame(() => {
          // 流式更新时使用平滑滚动，新消息或新会话时使用自动滚动
          scrollToBottom(isNewSession || isInitialLoad ? 'auto' : 'smooth')
        })
      }
      
      prevMessagesLengthRef.current = messages.length
      prevFirstMessageIdRef.current = firstMessageId
      prevLastMessageIdRef.current = lastMessageId
      prevLastMessageContentRef.current = lastMessageContent
    } else {
      prevMessagesLengthRef.current = 0
      prevFirstMessageIdRef.current = undefined
      prevLastMessageIdRef.current = undefined
      prevLastMessageContentRef.current = ''
    }
  }, [messages])

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto p-6 space-y-4">
      {messages.length === 0 ? (
        <div className="text-center text-gray-500 mt-20">
          <p>开始新的对话吧！</p>
        </div>
      ) : (
        <>
          {messages.map((message) => (
            <MessageItem key={message.id} message={message} />
          ))}
          <div ref={messagesEndRef} />
        </>
      )}
    </div>
  )
}

