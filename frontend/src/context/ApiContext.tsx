import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { setApiBaseUrl, getApiBaseUrl } from '../api/client'

const LS_KEY = 'deckr:api-base-url'

interface ApiContextValue {
  apiBaseUrl: string
  updateApiBaseUrl: (url: string) => void
  resetApiBaseUrl: () => void
}

const ApiContext = createContext<ApiContextValue>({
  apiBaseUrl: '',
  updateApiBaseUrl: () => {},
  resetApiBaseUrl: () => {},
})

export function ApiProvider({ children }: { children: ReactNode }) {
  const envUrl = (import.meta.env.VITE_API_BASE_URL as string) || ''

  const [apiBaseUrl, setUrl] = useState<string>(() => {
    try {
      return localStorage.getItem(LS_KEY) || envUrl
    } catch {
      return envUrl
    }
  })

  // Keep the module-level client variable in sync with context state.
  useEffect(() => {
    setApiBaseUrl(apiBaseUrl)
  }, [apiBaseUrl])

  const updateApiBaseUrl = (url: string) => {
    const trimmed = url.trim()
    try {
      if (trimmed) {
        localStorage.setItem(LS_KEY, trimmed)
      } else {
        localStorage.removeItem(LS_KEY)
      }
    } catch {
      // ignore storage errors
    }
    setUrl(trimmed)
  }

  const resetApiBaseUrl = () => {
    try {
      localStorage.removeItem(LS_KEY)
    } catch { /* ignore */ }
    setUrl(envUrl)
    setApiBaseUrl(envUrl)
  }

  return (
    <ApiContext.Provider value={{ apiBaseUrl, updateApiBaseUrl, resetApiBaseUrl }}>
      {children}
    </ApiContext.Provider>
  )
}

export const useApi = () => useContext(ApiContext)

// Convenience: read current base URL outside React (for non-hook callers).
export const readApiBaseUrl = getApiBaseUrl
