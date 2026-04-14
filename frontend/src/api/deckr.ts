import { get, post } from './client'

export interface DeckrResponse {
  content: string | null
  exists: boolean
}

export interface GenerateDeckrResponse {
  generated: boolean
  path: string
  source: string
}

export interface DeckrSectionResponse {
  section: string
  content: string
  saved: boolean
}

export const getDeckr = (): Promise<DeckrResponse> =>
  get<DeckrResponse>('/deckr')

export const generateDeckr = (sessionId: string): Promise<GenerateDeckrResponse> =>
  post<GenerateDeckrResponse>('/deckr/generate', { session_id: sessionId })

export const regenerateDeckrSection = (
  section: string,
  sessionId: string,
): Promise<DeckrSectionResponse> =>
  post<DeckrSectionResponse>('/deckr/section', { section, regenerate: true, session_id: sessionId })

export const saveDeckr = (content: string): Promise<{ saved: boolean; path: string }> =>
  post('/deckr/save', { content })
