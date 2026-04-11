import { useState, useCallback, useEffect } from 'react'
import * as workspaceApi from '../api/workspace'
import type { TreeNode } from '../types/workspace'

export function useWorkspace() {
  const [tree, setTree] = useState<TreeNode[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshTree = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await workspaceApi.getTree()
      setTree(res.items)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load workspace')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshTree()
  }, [refreshTree])

  const readFile = useCallback(async (path: string): Promise<string> => {
    const res = await workspaceApi.getFile(path)
    return res.content
  }, [])

  const writeFile = useCallback(
    async (path: string, content: string): Promise<void> => {
      await workspaceApi.writeFile(path, content)
    },
    [],
  )

  const deleteFile = useCallback(
    async (path: string): Promise<void> => {
      await workspaceApi.deleteFile(path)
      await refreshTree()
    },
    [refreshTree],
  )

  const createFolder = useCallback(
    async (path: string): Promise<void> => {
      await workspaceApi.createFolder(path)
      await refreshTree()
    },
    [refreshTree],
  )

  return {
    tree,
    loading,
    error,
    refreshTree,
    readFile,
    writeFile,
    deleteFile,
    createFolder,
  }
}
