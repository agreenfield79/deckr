import { useState, useEffect } from 'react'
import { useApi } from '../context/ApiContext'

/**
 * DevModePanel — visible only when `?devmode=1` is in the URL.
 * Allows overriding the backend API base URL for local dev / staging testing.
 */
export default function DevModePanel() {
  const { apiBaseUrl, updateApiBaseUrl, resetApiBaseUrl } = useApi()
  const [draft, setDraft] = useState(apiBaseUrl)
  const [show, setShow] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('devmode') === '1') setShow(true)
  }, [])

  useEffect(() => {
    setDraft(apiBaseUrl)
  }, [apiBaseUrl])

  if (!show) return null

  const handleApply = () => {
    updateApiBaseUrl(draft)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="shrink-0 flex items-center gap-2 px-4 py-2 bg-[#fff8e1] border-b border-[#f1c21b] text-xs text-[#524010]">
      <span className="font-semibold text-[#b28704] shrink-0">Dev Mode</span>
      <span className="text-[#6f6f6f] shrink-0">API Base URL:</span>
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleApply()}
        placeholder="http://localhost:8000"
        className="flex-1 max-w-xs px-2 py-0.5 border border-[#e0e0e0] rounded font-mono bg-white text-[#161616] text-xs focus:outline-none focus:border-[#f1c21b]"
      />
      <button
        onClick={handleApply}
        className="px-2 py-0.5 bg-[#f1c21b] text-[#161616] rounded font-medium hover:bg-[#d4ac0d] transition-colors"
      >
        {saved ? '✓ Saved' : 'Apply'}
      </button>
      <button
        onClick={() => { resetApiBaseUrl(); setDraft('') }}
        className="px-2 py-0.5 text-[#b28704] hover:underline"
      >
        Reset
      </button>
      <span className="ml-auto text-[#a8a8a8] shrink-0">
        Active: <code className="font-mono">{apiBaseUrl || '(relative)'}</code>
      </span>
    </div>
  )
}
