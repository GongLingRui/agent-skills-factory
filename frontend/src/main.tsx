import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { initThemeFromStorage } from '@/lib/theme'
import './index.css'

initThemeFromStorage()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
