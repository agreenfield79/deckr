export class ApiError extends Error {
  status: number
  code: string | undefined

  constructor(status: number, detail: string, code?: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

// Module-level base URL — updated at runtime by ApiContext when the user
// switches environments or uses DevModePanel (?devmode=1).
let _baseUrl: string = (import.meta.env.VITE_API_BASE_URL as string) || ''

export function setApiBaseUrl(url: string) {
  _baseUrl = url
}

export function getApiBaseUrl(): string {
  return _baseUrl
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const apiPath = path.startsWith('/api') ? path : `/api${path}`
  const url = _baseUrl ? `${_baseUrl}${apiPath}` : apiPath

  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
    ...options,
  })

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    let code: string | undefined

    try {
      const body = await response.json()
      if (body.detail) detail = body.detail
      if (body.code) code = body.code
    } catch {
      // non-JSON error body — use default message
    }

    throw new ApiError(response.status, detail, code)
  }

  // 204 No Content — return empty object
  if (response.status === 204) {
    return {} as T
  }

  return response.json() as Promise<T>
}

export const get = <T>(path: string): Promise<T> =>
  apiFetch<T>(path, { method: 'GET' })

export const post = <T>(path: string, body?: unknown): Promise<T> =>
  apiFetch<T>(path, {
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

export const del = <T>(path: string): Promise<T> =>
  apiFetch<T>(path, { method: 'DELETE' })

export const patch = <T>(path: string, body?: unknown): Promise<T> =>
  apiFetch<T>(path, {
    method: 'PATCH',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

export default apiFetch
