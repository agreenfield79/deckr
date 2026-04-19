/**
 * LimeExplanationChart — horizontal bar chart showing LIME local feature contributions.
 * Reuses the same Carbon SimpleBarChart pattern as ShapWaterfallChart.
 * Sources from GET /api/slacr/shap-lime → lime_values JSONB.
 */

import { SimpleBarChart } from '@carbon/charts-react'
import '@carbon/charts-react/styles.css'

interface Props {
  limeValues: Record<string, number> | null | undefined
}

export default function LimeExplanationChart({ limeValues }: Props) {
  if (!limeValues || Object.keys(limeValues).length === 0) {
    return (
      <p className="text-xs text-[#a8a8a8] italic mt-2">
        LIME values not yet available — run the pipeline to populate.
      </p>
    )
  }

  const sorted = Object.entries(limeValues)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 10)

  const data = sorted.map(([feature, value]) => ({
    group: feature,
    value: Math.round(value * 1000) / 1000,
  }))

  const options = {
    title: 'LIME Local Feature Contributions',
    axes: {
      left: { mapsTo: 'group', scaleType: 'labels' as const },
      bottom: { mapsTo: 'value', scaleType: 'linear' as const },
    },
    bars: {
      maxWidth: 18,
    },
    color: {
      scale: Object.fromEntries(
        sorted.map(([feature, value]) => [feature, value >= 0 ? '#da1e28' : '#24a148'])
      ),
    },
    height: '280px',
    toolbar: { enabled: false },
  } as Parameters<typeof SimpleBarChart>[0]['options']

  return (
    <div className="mt-3">
      <SimpleBarChart data={data} options={options} />
    </div>
  )
}
