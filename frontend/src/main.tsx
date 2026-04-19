import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@carbon/charts-react/styles.css'
import './styles/globals.css'
import App from './App.tsx'
import { ApiProvider } from './context/ApiContext'
import { ConfigProvider } from './context/ConfigContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ApiProvider>
      <ConfigProvider>
        <App />
      </ConfigProvider>
    </ApiProvider>
  </StrictMode>,
)
