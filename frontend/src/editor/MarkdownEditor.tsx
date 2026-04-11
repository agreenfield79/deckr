import { useState, useEffect, useRef, useCallback } from 'react'
import { Eye, Code } from 'lucide-react'
import clsx from 'clsx'
import MarkdownViewer from './MarkdownViewer'

interface MarkdownEditorProps {
  content: string
  filePath?: string
  onSave: (content: string) => Promise<void>
}

type SaveState = 'idle' | 'saving' | 'saved'

export default function MarkdownEditor({
  content: initialContent,
  filePath,
  onSave,
}: MarkdownEditorProps) {
  const [content, setContent] = useState(initialContent)
  const [mode, setMode] = useState<'edit' | 'preview'>('edit')
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync when a different file is opened
  useEffect(() => {
    setContent(initialContent)
    setSaveState('idle')
  }, [initialContent, filePath])

  const handleChange = useCallback(
    (value: string) => {
      setContent(value)
      setSaveState('saving')
      if (debounceRef.current) clearTimeout(debounceRef.current)
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current)

      debounceRef.current = setTimeout(async () => {
        try {
          await onSave(value)
          setSaveState('saved')
          savedTimerRef.current = setTimeout(() => setSaveState('idle'), 2000)
        } catch {
          setSaveState('idle')
        }
      }, 500)
    },
    [onSave],
  )

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[#e0e0e0] bg-[#f4f4f4] shrink-0">
        {filePath && (
          <span className="text-xs text-[#8d8d8d] font-mono truncate flex-1 min-w-0">
            {filePath}
          </span>
        )}
        <div className="flex items-center gap-1 ml-auto shrink-0">
          {saveState === 'saving' && (
            <span className="text-xs text-[#8d8d8d]">Saving…</span>
          )}
          {saveState === 'saved' && (
            <span className="text-xs text-[#24a148] font-medium">Saved</span>
          )}
          <button
            className={clsx(
              'flex items-center gap-1 px-2 py-0.5 text-xs rounded transition-colors',
              mode === 'edit'
                ? 'bg-[#0f62fe] text-white'
                : 'text-[#525252] hover:bg-[#e8e8e8]',
            )}
            onClick={() => setMode('edit')}
          >
            <Code size={11} />
            Edit
          </button>
          <button
            className={clsx(
              'flex items-center gap-1 px-2 py-0.5 text-xs rounded transition-colors',
              mode === 'preview'
                ? 'bg-[#0f62fe] text-white'
                : 'text-[#525252] hover:bg-[#e8e8e8]',
            )}
            onClick={() => setMode('preview')}
          >
            <Eye size={11} />
            Preview
          </button>
        </div>
      </div>

      {/* Content area */}
      {mode === 'edit' ? (
        <textarea
          className="flex-1 w-full px-4 py-3 font-mono text-xs text-[#161616] bg-white resize-none outline-none leading-relaxed"
          value={content}
          onChange={(e) => handleChange(e.target.value)}
          spellCheck={false}
          placeholder="Start typing…"
        />
      ) : (
        <div className="flex-1 overflow-y-auto px-6 py-5 bg-white">
          <MarkdownViewer content={content} />
        </div>
      )}
    </div>
  )
}
