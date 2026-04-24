import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react'

interface Toast {
  id: number
  type: 'success' | 'error' | 'info'
  message: string
}

interface ToastContextValue {
  success: (message: string) => void
  error: (message: string) => void
  info: (message: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

let _nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (type: 'success' | 'error' | 'info', message: string) => {
      const id = _nextId++
      setToasts((prev) => [...prev, { id, type, message }])
      setTimeout(() => dismiss(id), 3500)
    },
    [dismiss],
  )

  const success = useCallback((m: string) => push('success', m), [push])
  const error = useCallback((m: string) => push('error', m), [push])
  const info = useCallback((m: string) => push('info', m), [push])

  return (
    <ToastContext.Provider value={{ success, error, info }}>
      {children}
      {/* Toast stack — bottom-right */}
      <div className="fixed bottom-5 right-5 flex flex-col gap-2 z-50 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`flex items-center gap-2 px-4 py-2.5 rounded shadow-lg text-sm font-medium text-white pointer-events-auto
              ${t.type === 'success' ? 'bg-[#24a148]' : t.type === 'info' ? 'bg-[#0f62fe]' : 'bg-[#da1e28]'}`}
          >
            <span>{t.type === 'success' ? '✓' : t.type === 'info' ? 'ℹ' : '✕'}</span>
            <span>{t.message}</span>
            <button
              className="ml-2 opacity-70 hover:opacity-100 transition-opacity"
              onClick={() => dismiss(t.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
