import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react'
import { useWorkspace } from '../explorer/useWorkspace'
import type { ActiveFile, TreeNode } from '../types/workspace'

interface ProjectContextValue {
  projectName: string
  setProjectName: (name: string) => void
  activeFile: ActiveFile | null
  openFile: (path: string) => Promise<void>
  closeFile: () => void
  saveActiveFile: (content: string) => Promise<void>
  tree: TreeNode[]
  treeLoading: boolean
  refreshTree: () => Promise<void>
  readFile: (path: string) => Promise<string>
  writeFile: (path: string, content: string) => Promise<void>
  deleteFile: (path: string) => Promise<void>
  createFolder: (path: string) => Promise<void>
}

const ProjectContext = createContext<ProjectContextValue | null>(null)

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projectName, setProjectName] = useState('default')
  const [activeFile, setActiveFile] = useState<ActiveFile | null>(null)

  const {
    tree,
    loading: treeLoading,
    refreshTree,
    readFile,
    writeFile,
    deleteFile,
    createFolder,
  } = useWorkspace()

  const openFile = useCallback(
    async (path: string) => {
      const content = await readFile(path)
      setActiveFile({ path, content })
    },
    [readFile],
  )

  const closeFile = useCallback(() => setActiveFile(null), [])

  const saveActiveFile = useCallback(
    async (content: string) => {
      if (!activeFile) return
      await writeFile(activeFile.path, content)
      setActiveFile((prev) => (prev ? { ...prev, content } : null))
    },
    [activeFile, writeFile],
  )

  return (
    <ProjectContext.Provider
      value={{
        projectName,
        setProjectName,
        activeFile,
        openFile,
        closeFile,
        saveActiveFile,
        tree,
        treeLoading,
        refreshTree,
        readFile,
        writeFile,
        deleteFile,
        createFolder,
      }}
    >
      {children}
    </ProjectContext.Provider>
  )
}

export function useProject() {
  const ctx = useContext(ProjectContext)
  if (!ctx) throw new Error('useProject must be used within a ProjectProvider')
  return ctx
}
