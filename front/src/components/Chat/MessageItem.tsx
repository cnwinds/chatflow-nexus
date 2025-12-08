import { Message } from '../../types'
import { marked } from 'marked'
import { useMemo } from 'react'
import hljs from 'highlight.js'
// 使用适合浅色背景的代码高亮主题
import 'highlight.js/styles/github.css'

// 配置 marked 以保留换行符并支持代码高亮
marked.setOptions({
  breaks: true, // 将单个换行符转换为 <br>
  gfm: true, // 启用 GitHub Flavored Markdown，更好地支持列表
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch (err) {
        console.warn('代码高亮失败:', err)
      }
    }
    try {
      return hljs.highlightAuto(code).value
    } catch (err) {
      return code
    }
  },
})

interface MessageItemProps {
  message: Message
}

export default function MessageItem({ message }: MessageItemProps) {
  const isUser = message.role === 'user'
  const isStreaming = message.isStreaming && !isUser
  
  // 使用 useMemo 优化 markdown 解析性能，只在 content 变化时重新解析
  const htmlContent = useMemo(() => {
    if (!message.content) return ''
    try {
      // 预处理内容：确保列表格式正确
      // 将 "文本\n- 项目" 格式转换为 "文本\n\n- 项目"（列表前需要空行）
      let processedContent = message.content
      // 匹配 "非空白字符\n- " 或 "非空白字符\n* " 或 "非空白字符\n1. " 等列表模式
      // 在这些模式前添加一个换行符，确保列表能被正确识别
      processedContent = processedContent.replace(/([^\n])\n([-*]|\d+\.)\s/g, '$1\n\n$2 ')
      
      return marked(processedContent)
    } catch (error) {
      console.error('Markdown 解析失败:', error)
      // 如果解析失败，返回转义的 HTML
      return message.content.replace(/</g, '&lt;').replace(/>/g, '&gt;')
    }
  }, [message.content])

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-3xl rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-indigo-600 text-white'
            : 'bg-white border border-gray-200 text-gray-900'
        }`}
      >
        <div className={`prose prose-sm max-w-none ${isUser ? 'prose-invert' : ''} prose-pre:bg-gray-100 prose-pre:border prose-pre:border-gray-200`}>
          <div
            className="flex-1 markdown-content"
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

