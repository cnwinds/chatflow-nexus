import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
import { useThemeStore } from './stores/themeStore'
import Login from './components/Auth/Login'
import Chat from './components/Chat/Chat'
import AgentManager from './components/AgentManager/AgentManager'

function App() {
  const { isAuthenticated } = useAuthStore()
  const { theme } = useThemeStore()

  // 初始化主题
  useEffect(() => {
    document.documentElement.classList.remove('light', 'dark')
    document.documentElement.classList.add(theme)
  }, [theme])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={isAuthenticated ? <Chat /> : <Navigate to="/login" />}
        />
        <Route
          path="/agents"
          element={isAuthenticated ? <AgentManager /> : <Navigate to="/login" />}
        />
      </Routes>
    </BrowserRouter>
  )
}

export default App

