import { useRef, useLayoutEffect, useState, useEffect } from 'react'
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
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true)
  const isUserScrollingRef = useRef(false)
  const isAutoScrollingRef = useRef(false)
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // 检测是否在底部（允许一定的误差范围）
  const isAtBottom = (threshold: number = 50): boolean => {
    if (!containerRef.current) return true
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    return scrollHeight - scrollTop - clientHeight <= threshold
  }

  // 滚动到底部的函数
  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
    if (messagesEndRef.current) {
      isAutoScrollingRef.current = true
      messagesEndRef.current.scrollIntoView({ behavior })
      // 标记自动滚动结束（根据滚动行为设置不同的延迟）
      const delay = behavior === 'smooth' ? 500 : 100
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current)
      }
      scrollTimeoutRef.current = setTimeout(() => {
        isAutoScrollingRef.current = false
        // 自动滚动完成后，检查是否仍在底部，如果是则保持自动滚动
        if (isAtBottom()) {
          setShouldAutoScroll(true)
          isUserScrollingRef.current = false
        }
      }, delay)
    }
  }

  // 监听滚动事件，检测用户是否手动滚动
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const handleScroll = () => {
      // 忽略程序自动滚动
      if (isAutoScrollingRef.current) return
      
      const atBottom = isAtBottom()
      
      // 如果用户正在滚动，检测是否在底部
      if (isUserScrollingRef.current) {
        setShouldAutoScroll(atBottom)
        // 如果滚动到底部，重置用户滚动标志
        if (atBottom) {
          isUserScrollingRef.current = false
        }
      } else if (atBottom) {
        // 即使用户没有主动滚动，但如果已经在底部，也应该恢复自动滚动
        // 这处理了用户通过其他方式（如点击滚动条）滚动到底部的情况
        setShouldAutoScroll(true)
      }
    }

    // 监听鼠标滚轮和触摸滚动
    const handleWheel = () => {
      if (isAutoScrollingRef.current) return
      isUserScrollingRef.current = true
      const atBottom = isAtBottom()
      setShouldAutoScroll(atBottom)
    }

    const handleTouchStart = () => {
      if (isAutoScrollingRef.current) return
      isUserScrollingRef.current = true
    }

    const handleTouchMove = () => {
      if (isAutoScrollingRef.current) return
      const atBottom = isAtBottom()
      setShouldAutoScroll(atBottom)
    }

    // 监听键盘滚动（方向键、Page Up/Down等）
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isAutoScrollingRef.current) return
      const scrollKeys = ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']
      if (scrollKeys.includes(e.key)) {
        isUserScrollingRef.current = true
        // 延迟检测，等待滚动完成
        setTimeout(() => {
          const atBottom = isAtBottom()
          setShouldAutoScroll(atBottom)
        }, 100)
      }
    }

    // 监听鼠标拖动滚动条
    const handleMouseDown = () => {
      if (isAutoScrollingRef.current) return
      isUserScrollingRef.current = true
    }

    container.addEventListener('scroll', handleScroll)
    container.addEventListener('wheel', handleWheel, { passive: true })
    container.addEventListener('touchstart', handleTouchStart, { passive: true })
    container.addEventListener('touchmove', handleTouchMove, { passive: true })
    container.addEventListener('mousedown', handleMouseDown)
    window.addEventListener('keydown', handleKeyDown)

    return () => {
      container.removeEventListener('scroll', handleScroll)
      container.removeEventListener('wheel', handleWheel)
      container.removeEventListener('touchstart', handleTouchStart)
      container.removeEventListener('touchmove', handleTouchMove)
      container.removeEventListener('mousedown', handleMouseDown)
      window.removeEventListener('keydown', handleKeyDown)
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current)
      }
    }
  }, [])

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
      
      // 首次输出或新消息时，强制滚动到底部并启用自动滚动
      if (isNewSession || isInitialLoad || isNewMessage) {
        setShouldAutoScroll(true)
        isUserScrollingRef.current = false
        // 使用 requestAnimationFrame 确保在浏览器重绘前执行
        requestAnimationFrame(() => {
          scrollToBottom(isNewSession || isInitialLoad ? 'auto' : 'smooth')
        })
      }
      // 流式更新时，只有在用户没有手动滚动时才自动滚动
      else if (isStreamingUpdate && shouldAutoScroll) {
        // 使用 requestAnimationFrame 确保在浏览器重绘前执行
        requestAnimationFrame(() => {
          scrollToBottom('smooth')
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
      setShouldAutoScroll(true)
      isUserScrollingRef.current = false
    }
  }, [messages, shouldAutoScroll])

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto p-6 space-y-4 bg-bg-primary">
      {messages.length === 0 ? (
        <div className="text-center text-text-secondary mt-20">
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

