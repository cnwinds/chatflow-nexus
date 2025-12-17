/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class', // 使用 class 策略来切换暗色模式
  theme: {
    extend: {
      colors: {
        // 使用 CSS 变量定义颜色，支持主题切换
        bg: {
          primary: 'var(--bg-primary)',
          secondary: 'var(--bg-secondary)',
          tertiary: 'var(--bg-tertiary)',
          hover: 'var(--bg-hover)',
          active: 'var(--bg-active)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          tertiary: 'var(--text-tertiary)',
          inverse: 'var(--text-inverse)',
        },
        border: {
          primary: 'var(--border-primary)',
          secondary: 'var(--border-secondary)',
        },
        accent: {
          primary: 'var(--accent-primary)',
          hover: 'var(--accent-hover)',
          active: 'var(--accent-active)',
        },
        message: {
          user: 'var(--message-user)',
          assistant: 'var(--message-assistant)',
          userText: 'var(--message-user-text)',
          assistantText: 'var(--message-assistant-text)',
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}

