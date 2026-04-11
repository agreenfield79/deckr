import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import clsx from 'clsx'

interface MarkdownViewerProps {
  content: string
  className?: string
}

export default function MarkdownViewer({ content, className }: MarkdownViewerProps) {
  return (
    <div className={clsx('prose prose-sm max-w-none', className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}
