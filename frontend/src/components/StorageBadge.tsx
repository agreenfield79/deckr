import { useConfig } from '../context/ConfigContext'

/**
 * StorageBadge — shows the current storage backend in the app header.
 * Reads storage_mode from the /api/health response via ConfigContext.
 */
export default function StorageBadge() {
  const { health } = useConfig()

  const storageMode = health?.storage_mode ?? health?.config?.STORAGE_BACKEND ?? 'local'
  const isCloud = storageMode === 'cloud'

  return (
    <span
      title={`Storage backend: ${storageMode}`}
      className={`text-[10px] font-medium px-1.5 py-0.5 rounded select-none ${
        isCloud
          ? 'bg-[#defbe6] text-[#198038]'
          : 'bg-[#e8e8e8] text-[#525252]'
      }`}
    >
      {isCloud ? 'Cloud (GCP)' : 'Local'}
    </span>
  )
}
