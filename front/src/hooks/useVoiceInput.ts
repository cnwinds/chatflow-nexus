import { useState, useRef, useCallback } from 'react'
import { getWebSocketClient } from '../services/websocket'
import { ListenMessage } from '../types/websocket'

interface UseVoiceInputOptions {
  sessionId?: string
  agentId?: number
  onTranscript?: (text: string) => void
  onError?: (error: Error) => void
}

export function useVoiceInput(options: UseVoiceInputOptions = {}) {
  const { sessionId, agentId, onTranscript, onError } = options
  const [isRecording, setIsRecording] = useState(false)
  const [isSupported, setIsSupported] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioStreamRef = useRef<MediaStream | null>(null)
  const wsClientRef = useRef(getWebSocketClient())

  // 检查浏览器支持
  const checkSupport = useCallback(async () => {
    try {
      // 检查 MediaRecorder 支持
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setIsSupported(false)
        return false
      }

      // 检查 MediaRecorder 是否支持 Opus（必须支持，服务端要求）
      // 注意：这里只检查 Opus 支持，不支持回退到其他格式
      const opusSupported = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ||
                           MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
      
      setIsSupported(opusSupported)
      return opusSupported
    } catch (error) {
      console.error('检查浏览器支持失败:', error)
      setIsSupported(false)
      return false
    }
  }, [])

  // 开始录音
  const startRecording = useCallback(async () => {
    try {
      const wsClient = wsClientRef.current

      // 确保 WebSocket 已连接
      if (!wsClient.isConnected()) {
        await wsClient.connect()
      }

      // 获取麦克风权限
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      })

      audioStreamRef.current = stream

      // 确定使用的 MIME 类型（必须使用 Opus 格式，服务端要求）
      let mimeType: string | null = null
      
      // 优先尝试 audio/webm;codecs=opus（Chrome、Edge、Firefox 支持）
      if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
        mimeType = 'audio/webm;codecs=opus'
      }
      // 其次尝试 audio/ogg;codecs=opus（Firefox 支持）
      else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
        mimeType = 'audio/ogg;codecs=opus'
      }
      // 如果都不支持，抛出错误（服务端要求必须是 Opus 格式）
      else {
        throw new Error('浏览器不支持 Opus 音频编码，无法使用语音输入功能。请使用 Chrome、Firefox 或 Edge 浏览器。')
      }

      // 创建 MediaRecorder（必须使用 Opus 格式）
      const options: MediaRecorderOptions = {
        mimeType: mimeType,
        audioBitsPerSecond: 16000, // 16kbps for Opus（服务端要求）
      }
      
      const mediaRecorder = new MediaRecorder(stream, options)
      
      // 验证实际使用的 MIME 类型
      const actualMimeType = mediaRecorder.mimeType || mimeType
      if (!actualMimeType.includes('opus')) {
        throw new Error(`音频编码格式错误：期望 Opus 格式，但实际为 ${actualMimeType}`)
      }

      mediaRecorderRef.current = mediaRecorder

      // 处理数据可用事件
      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          // 发送音频数据到服务器
          event.data.arrayBuffer().then((buffer) => {
            try {
              wsClient.sendBinary(buffer)
            } catch (error) {
              console.error('发送音频数据失败:', error)
              onError?.(error as Error)
            }
          })
        }
      }

      // 开始录音
      mediaRecorder.start(60) // 每 60ms 发送一次数据（与后端配置一致）

      // 发送 listen start 消息
      const listenMessage: ListenMessage = {
        type: 'listen',
        state: 'start',
        mode: 'realtime',
        session_id: sessionId,
        agent_id: agentId,
      }
      wsClient.sendListen(listenMessage)

      setIsRecording(true)
    } catch (error) {
      console.error('开始录音失败:', error)
      setIsRecording(false)
      onError?.(error as Error)
      
      // 清理资源
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach(track => track.stop())
        audioStreamRef.current = null
      }
    }
  }, [sessionId, onError])

  // 停止录音
  const stopRecording = useCallback(() => {
    try {
      const wsClient = wsClientRef.current

      // 停止 MediaRecorder
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }

      // 停止音频流
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach(track => track.stop())
        audioStreamRef.current = null
      }

      // 发送 listen stop 消息
      const listenMessage: ListenMessage = {
        type: 'listen',
        state: 'stop',
        session_id: sessionId,
        agent_id: agentId,
      }
      wsClient.sendListen(listenMessage)

      setIsRecording(false)
    } catch (error) {
      console.error('停止录音失败:', error)
      onError?.(error as Error)
      setIsRecording(false)
    }
  }, [sessionId, agentId, onError])

  // 切换录音状态
  const toggleRecording = useCallback(() => {
    if (isRecording) {
      stopRecording()
    } else {
      startRecording()
    }
  }, [isRecording, startRecording, stopRecording])

  return {
    isRecording,
    isSupported,
    startRecording,
    stopRecording,
    toggleRecording,
    checkSupport,
  }
}

