import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import ThemeToggle from '../ThemeToggle'

export default function Login() {
  const [loginName, setLoginName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login, isAuthenticated, checkAuth } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    checkAuth()
    if (isAuthenticated) {
      navigate('/')
    }
  }, [isAuthenticated, navigate, checkAuth])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await login(loginName, password)
      navigate('/')
    } catch (err: any) {
      setError(err.response?.data?.detail || '登录失败，请检查用户名和密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-secondary">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <div className="max-w-md w-full space-y-8 p-8 bg-bg-primary rounded-lg shadow-md border border-border-primary">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-text-primary">
            登录到AI对话服务
          </h2>
        </div>
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded">
              {error}
            </div>
          )}
          <div className="rounded-md shadow-sm -space-y-px">
            <div>
              <label htmlFor="login-name" className="sr-only">登录名</label>
              <input
                id="login-name"
                type="text"
                required
                value={loginName}
                onChange={(e) => setLoginName(e.target.value)}
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-border-primary bg-bg-primary placeholder:text-text-tertiary text-text-primary rounded-t-md focus:outline-none focus:ring-accent-primary focus:border-accent-primary focus:z-10 sm:text-sm transition-colors"
                placeholder="登录名（手机号/邮箱/用户名）"
              />
            </div>
            <div>
              <label htmlFor="password" className="sr-only">密码</label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-border-primary bg-bg-primary placeholder:text-text-tertiary text-text-primary rounded-b-md focus:outline-none focus:ring-accent-primary focus:border-accent-primary focus:z-10 sm:text-sm transition-colors"
                placeholder="密码"
              />
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled={loading}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-text-inverse bg-accent-primary hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent-primary disabled:opacity-50 transition-colors"
            >
              {loading ? '登录中...' : '登录'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

