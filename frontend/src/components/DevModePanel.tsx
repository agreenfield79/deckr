import { useState, useEffect } from 'react'
import { useApi } from '../context/ApiContext'
import { useToast } from '../context/ToastContext'
import { useProject } from '../context/ProjectContext'
import { resetPipelineData } from '../api/admin'
import { ApiError } from '../api/client'

/**
 * DevModePanel — visible only when `?devmode=1` is in the URL.
 * Allows overriding the backend API base URL for local dev / staging testing.
 * Also exposes the Reset Pipeline Data action for clearing all database tiers
 * before a demo session.
 */
export default function DevModePanel() {
  const { apiBaseUrl, updateApiBaseUrl, resetApiBaseUrl } = useApi()
  const toast = useToast()
  const { refreshTree } = useProject()

  const [draft, setDraft] = useState(apiBaseUrl)
  const [show, setShow] = useState(false)
  const [saved, setSaved] = useState(false)
  const [confirmPending, setConfirmPending] = useState(false)
  const [resetting, setResetting] = useState(false)

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

  const handleResetClick = () => {
    setConfirmPending(true)
  }

  const handleResetCancel = () => {
    setConfirmPending(false)
  }

  const handleResetConfirm = async () => {
    setConfirmPending(false)
    setResetting(true)
    try {
      await resetPipelineData()
      toast.info('Pipeline data cleared.')
      await refreshTree()
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 409
          ? 'Reset failed — a pipeline run may be active. Try again after completion.'
          : err instanceof ApiError
            ? `Reset failed: ${err.message}`
            : 'Reset failed — check backend logs.'
      toast.error(message)
    } finally {
      setResetting(false)
    }
  }

  return (
    <div className="shrink-0 flex items-center gap-2 px-4 py-2 bg-[#fff8e1] border-b border-[#f1c21b] text-xs text-[#524010]">
      {/* ── API base URL controls ── */}
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

      {/* ── Divider ── */}
      <span className="text-[#e0e0e0] select-none">|</span>

      {/* ── Reset Pipeline Data ── */}
      {!confirmPending ? (
        <button
          onClick={handleResetClick}
          disabled={resetting}
          className="px-2 py-0.5 border border-[#da1e28] text-[#da1e28] rounded font-medium
                     hover:bg-[#da1e28] hover:text-white transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
        >
          {resetting ? 'Resetting…' : 'Reset Pipeline Data'}
        </button>
      ) : (
        <span className="flex items-center gap-1.5 shrink-0">
          <span className="text-[#da1e28] font-medium">
            Wipe all DB records and vector indexes? This cannot be undone.
          </span>
          <button
            onClick={handleResetConfirm}
            className="px-2 py-0.5 bg-[#da1e28] text-white rounded font-medium hover:bg-[#b01c24] transition-colors"
          >
            Confirm
          </button>
          <button
            onClick={handleResetCancel}
            className="px-2 py-0.5 text-[#6f6f6f] hover:underline"
          >
            Cancel
          </button>
        </span>
      )}

      <span className="ml-auto text-[#a8a8a8] shrink-0">
        Active: <code className="font-mono">{apiBaseUrl || '(relative)'}</code>
      </span>
    </div>
  )
}
