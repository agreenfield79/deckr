import { useState } from 'react'

export function useSession() {
  const [sessionId] = useState<string>(() => {
    const stored = localStorage.getItem('deckr_session_id')
    if (stored) return stored
    const id = crypto.randomUUID()
    localStorage.setItem('deckr_session_id', id)
    return id
  })

  return { sessionId }
}
