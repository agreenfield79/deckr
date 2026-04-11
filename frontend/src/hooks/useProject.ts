import { useSession } from './useSession'
import { useProject as useProjectCtx } from '../context/ProjectContext'

/**
 * Focused hook that pairs projectName + sessionId for all agent and workspace API calls.
 * sessionId is required from Day 1 — it becomes the Orchestrate memory scope key in Phase 12.
 */
export function useProject() {
  const { sessionId } = useSession()
  const { projectName, setProjectName } = useProjectCtx()
  return { projectName, sessionId, setProjectName }
}
