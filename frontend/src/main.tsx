import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import AuthToolbar from './AuthToolbar.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthToolbar />
    <App />
  </StrictMode>,
)
