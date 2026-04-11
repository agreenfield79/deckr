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

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = path.startsWith('/api') ? path : `/api${path}`

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

export default apiFetch
