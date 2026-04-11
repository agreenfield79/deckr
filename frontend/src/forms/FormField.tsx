import { Plus, Trash2 } from 'lucide-react'
import clsx from 'clsx'

// ---------------------------------------------------------------------------
// Column definition for table-builder and list-builder
// ---------------------------------------------------------------------------
export interface TableColumn {
  key: string
  header: string
  type?: 'text' | 'number'
  placeholder?: string
  width?: string
}

// ---------------------------------------------------------------------------
// Per-variant prop types
// ---------------------------------------------------------------------------
interface BaseProps {
  label: string
  hint?: string
  error?: string
  required?: boolean
}

interface TextProps extends BaseProps {
  type: 'text'
  value: string
  onChange: (v: string) => void
  placeholder?: string
}

interface NumberProps extends BaseProps {
  type: 'number'
  value: number | ''
  onChange: (v: number | '') => void
  placeholder?: string
  prefix?: string
}

interface SelectProps extends BaseProps {
  type: 'select'
  value: string
  onChange: (v: string) => void
  options: Array<{ value: string; label: string }>
}

interface TextareaProps extends BaseProps {
  type: 'textarea'
  value: string
  onChange: (v: string) => void
  rows?: number
  placeholder?: string
}

interface TableBuilderProps extends BaseProps {
  type: 'table-builder'
  columns: TableColumn[]
  rows: Record<string, string | number>[]
  onChange: (rows: Record<string, string | number>[]) => void
  addLabel?: string
}

// Simple add/remove string list (for collateral)
interface ListBuilderProps extends BaseProps {
  type: 'list-builder'
  items: string[]
  onChange: (items: string[]) => void
  placeholder?: string
  addLabel?: string
}

type FormFieldProps =
  | TextProps
  | NumberProps
  | SelectProps
  | TextareaProps
  | TableBuilderProps
  | ListBuilderProps

// ---------------------------------------------------------------------------
// Shared styles
// ---------------------------------------------------------------------------
const inputBase =
  'w-full px-3 py-2 text-sm text-[#161616] bg-white border border-[#8d8d8d] rounded focus:outline-none focus:ring-2 focus:ring-[#0f62fe] focus:border-transparent transition-colors'

const cellInput =
  'w-full px-2 py-1 text-xs text-[#161616] bg-transparent border border-transparent rounded focus:border-[#0f62fe] focus:outline-none transition-colors'

// ---------------------------------------------------------------------------
// FormField
// ---------------------------------------------------------------------------
export default function FormField(props: FormFieldProps) {
  const { label, hint, error, required } = props

  const renderField = () => {
    switch (props.type) {
      case 'text':
        return (
          <input
            type="text"
            className={clsx(inputBase, error && 'border-[#da1e28]')}
            value={props.value}
            onChange={(e) => props.onChange(e.target.value)}
            placeholder={props.placeholder}
          />
        )

      case 'number':
        return (
          <div className="relative">
            {props.prefix && (
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-[#525252] pointer-events-none">
                {props.prefix}
              </span>
            )}
            <input
              type="number"
              className={clsx(
                inputBase,
                error && 'border-[#da1e28]',
                props.prefix && 'pl-6',
              )}
              value={props.value}
              onChange={(e) =>
                props.onChange(e.target.value === '' ? '' : Number(e.target.value))
              }
              placeholder={props.placeholder}
            />
          </div>
        )

      case 'select':
        return (
          <select
            className={clsx(inputBase, 'cursor-pointer', error && 'border-[#da1e28]')}
            value={props.value}
            onChange={(e) => props.onChange(e.target.value)}
          >
            <option value="">Select…</option>
            {props.options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        )

      case 'textarea':
        return (
          <textarea
            className={clsx(inputBase, 'resize-none', error && 'border-[#da1e28]')}
            rows={props.rows ?? 3}
            value={props.value}
            onChange={(e) => props.onChange(e.target.value)}
            placeholder={props.placeholder}
          />
        )

      case 'table-builder': {
        const { columns, rows, onChange, addLabel } = props

        const addRow = () => {
          const empty: Record<string, string | number> = {}
          columns.forEach((c) => { empty[c.key] = '' })
          onChange([...rows, empty])
        }

        const updateRow = (i: number, key: string, val: string | number) =>
          onChange(rows.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)))

        const removeRow = (i: number) =>
          onChange(rows.filter((_, idx) => idx !== i))

        const colStyle = { gridTemplateColumns: `repeat(${columns.length}, 1fr) 2rem` }

        return (
          <div className="space-y-2">
            {rows.length > 0 && (
              <div className="border border-[#e0e0e0] rounded overflow-hidden text-xs">
                <div className="grid bg-[#f4f4f4] border-b border-[#e0e0e0]" style={colStyle}>
                  {columns.map((c) => (
                    <div key={c.key} className="px-2 py-1.5 font-medium text-[#525252]">
                      {c.header}
                    </div>
                  ))}
                  <div />
                </div>
                {rows.map((row, ri) => (
                  <div key={ri} className="grid border-b last:border-b-0 border-[#e0e0e0]" style={colStyle}>
                    {columns.map((c) => (
                      <div key={c.key} className="px-1 py-0.5">
                        <input
                          type={c.type === 'number' ? 'number' : 'text'}
                          className={cellInput}
                          value={row[c.key] ?? ''}
                          onChange={(e) =>
                            updateRow(ri, c.key, c.type === 'number' ? Number(e.target.value) : e.target.value)
                          }
                          placeholder={c.placeholder}
                        />
                      </div>
                    ))}
                    <div className="flex items-center justify-center">
                      <button
                        type="button"
                        className="p-1 text-[#8d8d8d] hover:text-[#da1e28] transition-colors"
                        onClick={() => removeRow(ri)}
                        title="Remove"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <button
              type="button"
              className="flex items-center gap-1 px-2 py-1 text-xs text-[#0f62fe] hover:bg-[#edf4ff] rounded transition-colors"
              onClick={addRow}
            >
              <Plus size={12} />
              {addLabel ?? 'Add row'}
            </button>
          </div>
        )
      }

      case 'list-builder': {
        const { items, onChange, placeholder, addLabel } = props

        const addItem = () => onChange([...items, ''])

        const updateItem = (i: number, val: string) =>
          onChange(items.map((item, idx) => (idx === i ? val : item)))

        const removeItem = (i: number) =>
          onChange(items.filter((_, idx) => idx !== i))

        return (
          <div className="space-y-1.5">
            {items.map((item, i) => (
              <div key={i} className="flex items-center gap-1">
                <input
                  type="text"
                  className={clsx(inputBase, 'flex-1')}
                  value={item}
                  onChange={(e) => updateItem(i, e.target.value)}
                  placeholder={placeholder}
                />
                <button
                  type="button"
                  className="p-2 text-[#8d8d8d] hover:text-[#da1e28] transition-colors shrink-0"
                  onClick={() => removeItem(i)}
                  title="Remove"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
            <button
              type="button"
              className="flex items-center gap-1 px-2 py-1 text-xs text-[#0f62fe] hover:bg-[#edf4ff] rounded transition-colors"
              onClick={addItem}
            >
              <Plus size={12} />
              {addLabel ?? 'Add item'}
            </button>
          </div>
        )
      }
    }
  }

  return (
    <div>
      <label className="block text-xs font-medium text-[#161616] mb-1">
        {label}
        {required && <span className="text-[#da1e28] ml-0.5">*</span>}
      </label>
      {renderField()}
      {hint && !error && <p className="mt-1 text-xs text-[#525252]">{hint}</p>}
      {error && <p className="mt-1 text-xs text-[#da1e28]">{error}</p>}
    </div>
  )
}
