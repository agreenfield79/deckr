import { get, post } from './client'
import type { SlacrInput, SlacrOutput } from '../types/slacr'

export const getScore = (): Promise<SlacrOutput> =>
  get<SlacrOutput>('/risk/score')

export const postScore = (input: SlacrInput): Promise<SlacrOutput> =>
  post<SlacrOutput>('/risk/score', input)
