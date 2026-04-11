import { get } from './client'

export interface UploadedFile {
  name: string
  path: string
  size: number
  modified: number
  extracted: boolean
}

export interface UploadResponse {
  saved: boolean
  path: string
  filename: string
  extraction_queued: boolean
}

export async function uploadFile(
  file: File,
  category: string,
): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('category', category)
  // Use raw fetch — browser must set Content-Type with multipart boundary automatically
  const res = await fetch('/api/upload', { method: 'POST', body: formData })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `Upload failed (${res.status})`)
  }
  return res.json()
}

export const listUploads = (folder: string) =>
  get<UploadedFile[]>(`/upload/list?folder=${encodeURIComponent(folder)}`)
