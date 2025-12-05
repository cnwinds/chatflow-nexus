import { Message } from '../../types'
import { marked } from 'marked'

// 配置 marked 以保留换行符
marked.setOptions({
  breaks: true, // 将单个换行符转换为 <br>
})

interface MessageItemProps {
  message: Message
}

export default function MessageItem({ message }: MessageItemProps) {
  const isUser = message.role === 'user'
  const isStreaming = message.isStreaming && !isUser
  const htmlContent = marked(message.content || '')

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-3xl rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-indigo-600 text-white'
            : 'bg-white border border-gray-200 text-gray-900'
        }`}
      >
        <div className="prose prose-sm max-w-none">
          <div
            className="flex-1"
            dangerouslySetInnerHTML={{ __html: htmlContent }}
          />
          {isStreaming && (
            <span className="inline-block w-2 h-4 bg-gray-600 ml-1 animate-pulse" />
          )}
        </div>
        <div className={`text-xs mt-2 flex items-center ${isUser ? 'text-indigo-100' : 'text-gray-500'}`}>
          <span>{new Date(message.created_at).toLocaleTimeString()}</span>
          {isStreaming && (
            <span className="ml-2 text-gray-400 flex items-center gap-1">
              <span>正在输入</span>
              <span className="flex gap-0.5">
                <span className="w-1 h-1 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1 h-1 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1 h-1 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

