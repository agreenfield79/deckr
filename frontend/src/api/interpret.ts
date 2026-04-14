import { get, post } from './client'

// ---------------------------------------------------------------------------
// Shared types (mirrors backend/models/neural_slacr_output.py)
// ---------------------------------------------------------------------------

export interface FeatureImportanceItem {
  feature: string
  importance: number
  direction: string // "risk" — higher importance = stronger predictor of risk tier
}

export interface ScoreBandItem {
  rating: string
  count: number
  percentage: number // % of training set predicted in this band
}

export interface NeuralSlacrOutput {
  predicted_rating: string    // e.g. "Moderate Risk"
  probability: number         // model confidence 0–1
  composite_score: number     // weighted SLACR composite from analyst scores

  shap_values: Record<string, number>       // feature → SHAP contribution (predicted class)
  lime_coefficients: Record<string, number> // feature → LIME local coefficient

  feature_importances: FeatureImportanceItem[] // sorted by importance desc
  score_distribution: ScoreBandItem[]          // training-set distribution by band
  correlation_matrix: number[][]               // 9×9 Pearson correlation matrix

  feature_names: string[]           // ordered feature labels (length 9)
  input_values: Record<string, number> // the 9 input values fed to the model
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * POST /api/interpret/run
 * Triggers the Neural SLACR model + interpreter agent.
 * Writes SLACR/neural_slacr_output.json and Agent Notes/neural_slacr.md.
 * Returns NeuralSlacrOutput for immediate chart rendering.
 */
export const postRunInterpreter = (sessionId: string): Promise<NeuralSlacrOutput> =>
  post<NeuralSlacrOutput>('/interpret/run', { session_id: sessionId })

/**
 * GET /api/interpret/output
 * Reads SLACR/neural_slacr_output.json without re-triggering the model.
 * InterpretTab calls this on mount to restore last-run state.
 */
export const getNeuralSlacrOutput = (): Promise<NeuralSlacrOutput> =>
  get<NeuralSlacrOutput>('/interpret/output')
