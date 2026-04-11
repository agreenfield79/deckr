import { get, post } from './client'

export interface DeckResponse {
  content: string | null
  exists: boolean
}

export interface GenerateDeckResponse {
  generated: boolean
  path: string
  source: 'full_package' | 'agent_notes'
  sections_loaded: number
}

export interface SectionResponse {
  section: string
  content: string
  saved: boolean
}

export const getDeck = (): Promise<DeckResponse> =>
  get<DeckResponse>('/deck')

export const generateDeck = (sessionId: string): Promise<GenerateDeckResponse> =>
  post<GenerateDeckResponse>('/deck/generate', { session_id: sessionId })

export const regenerateSection = (
  section: string,
  sessionId: string,
): Promise<SectionResponse> =>
  post<SectionResponse>('/deck/section', { section, regenerate: true, session_id: sessionId })

export const saveDeck = (content: string): Promise<{ saved: boolean; path: string }> =>
  post('/deck/save', { content })
