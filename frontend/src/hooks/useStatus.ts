import { useState, useCallback, useEffect } from 'react'
import { get } from '../api/client'

export interface StatusItem {
  label: string
  complete: boolean
  path: string
  tab: string | null
  action: string | null
}

export interface StatusData {
  items: StatusItem[]
  percentage: number
}

export function useStatus() {
  const [data, setData] = useState<StatusData>({ items: [], percentage: 0 })
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await get<StatusData>('/status')
      setData(res)
    } catch {
      // fail silently — status is non-critical
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { items: data.items, percentage: data.percentage, loading, refresh }
}
