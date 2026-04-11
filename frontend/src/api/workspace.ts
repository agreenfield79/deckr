import { get, post, del } from './client'
import type { TreeResponse } from '../types/workspace'

export const getTree = () =>
  get<TreeResponse>('/workspace/tree')

export const getFile = (path: string) =>
  get<{ content: string }>(`/workspace/file?path=${encodeURIComponent(path)}`)

export const writeFile = (path: string, content: string) =>
  post<{ saved: boolean; path: string }>('/workspace/file', { path, content })

export const deleteFile = (path: string) =>
  del<{ deleted: boolean; path: string }>(
    `/workspace/file?path=${encodeURIComponent(path)}`,
  )

export const createFolder = (path: string) =>
  post<{ created: boolean; path: string }>('/workspace/folder', { path })
