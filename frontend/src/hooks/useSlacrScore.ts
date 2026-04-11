import { useState, useCallback, useMemo, useEffect } from 'react'
import * as slacrApi from '../api/slacr'
import * as agentApi from '../api/agent'
import type { SlacrInput, SlacrOutput } from '../types/slacr'

const DEFAULT_INPUT: SlacrInput = {
  strength:        3,
  leverage:        3,
  ability_to_repay: 3,
  collateral:      3,
  risk_factors:    3,
  notes:           {},
}

export function useSlacrScore() {
  const [scores, setScores] = useState<SlacrInput>({ ...DEFAULT_INPUT })
  const [result, setResult] = useState<SlacrOutput | null>(null)
  const [loading, setLoading] = useState(false)
  const [agentRunning, setAgentRunning] = useState(false)

  // Load existing score on mount
  useEffect(() => {
    slacrApi.getScore()
      .then((output) => {
        setResult(output)
        setScores(output.input)
      })
      .catch(() => {/* no score yet — use defaults */})
  }, [])

  const setScore = useCallback(
    (field: keyof Omit<SlacrInput, 'notes'>, value: number) => {
      setScores((prev) => ({ ...prev, [field]: value }))
    },
    [],
  )

  const setNote = useCallback((category: string, text: string) => {
    setScores((prev) => ({ ...prev, notes: { ...prev.notes, [category]: text } }))
  }, [])

  // Live score computed in browser from current slider values (no API call)
  const liveScore = useMemo(
    () =>
      scores.strength        * 0.20 +
      scores.leverage        * 0.20 +
      scores.ability_to_repay * 0.25 +
      scores.collateral      * 0.15 +
      scores.risk_factors    * 0.20,
    [scores],
  )

  const submit = useCallback(async (): Promise<SlacrOutput | null> => {
    setLoading(true)
    try {
      const output = await slacrApi.postScore(scores)
      setResult(output)
      return output
    } catch {
      return null
    } finally {
      setLoading(false)
    }
  }, [scores])

  const runAgent = useCallback(async (sessionId: string) => {
    setAgentRunning(true)
    try {
      return await agentApi.runAgent('risk', sessionId)
    } finally {
      setAgentRunning(false)
    }
  }, [])

  return {
    scores,
    result,
    loading,
    agentRunning,
    liveScore,
    setScore,
    setNote,
    submit,
    runAgent,
  }
}
