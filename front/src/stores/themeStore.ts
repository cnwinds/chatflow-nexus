import { create } from 'zustand'

type Theme = 'light' | 'dark'

interface ThemeState {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

// 从 localStorage 读取初始主题
const getInitialTheme = (): Theme => {
  try {
    const stored = localStorage.getItem('theme-storage')
    if (stored) {
      const parsed = JSON.parse(stored)
      return parsed.state?.theme || 'light'
    }
  } catch {}
  return 'light'
}

// 应用主题到 HTML 元素
const applyTheme = (theme: Theme) => {
  document.documentElement.classList.remove('light', 'dark')
  document.documentElement.classList.add(theme)
}

// 初始化主题
const initialTheme = getInitialTheme()
applyTheme(initialTheme)

export const useThemeStore = create<ThemeState>((set) => ({
  theme: initialTheme,
  setTheme: (theme) => {
    set({ theme })
    applyTheme(theme)
    // 持久化到 localStorage
    try {
      localStorage.setItem('theme-storage', JSON.stringify({ state: { theme } }))
    } catch {}
  },
  toggleTheme: () => {
    set((state) => {
      const newTheme = state.theme === 'light' ? 'dark' : 'light'
      applyTheme(newTheme)
      // 持久化到 localStorage
      try {
        localStorage.setItem('theme-storage', JSON.stringify({ state: { theme: newTheme } }))
      } catch {}
      return { theme: newTheme }
    })
  },
}))


