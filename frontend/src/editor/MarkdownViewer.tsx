import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import clsx from 'clsx'

interface MarkdownViewerProps {
  content: string
  className?: string
  textSize?: string   // overrides prose-sm's 0.875rem base font-size
}

export default function MarkdownViewer({ content, className, textSize }: MarkdownViewerProps) {
  return (
    <div
      className={clsx('prose prose-sm max-w-none', className)}
      style={textSize ? { fontSize: textSize } : undefined}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}
