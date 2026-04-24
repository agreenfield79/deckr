import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { getHealth, type HealthResponse } from '../api/health'

interface ConfigContextValue {
  health: HealthResponse | null
  healthLoading: boolean
  refreshHealth: () => void
}

const ConfigContext = createContext<ConfigContextValue>({
  health: null,
  healthLoading: true,
  refreshHealth: () => {},
})

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)

  const fetchHealth = () => {
    setHealthLoading(true)
    getHealth()
      .then((h) => setHealth(h))
      .catch(() => setHealth(null))
      .finally(() => setHealthLoading(false))
  }

  useEffect(() => {
    fetchHealth()
  }, [])

  return (
    <ConfigContext.Provider value={{ health, healthLoading, refreshHealth: fetchHealth }}>
      {children}
    </ConfigContext.Provider>
  )
}

export const useConfig = () => useContext(ConfigContext)
