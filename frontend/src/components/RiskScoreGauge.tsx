/**
 * RiskScoreGauge — SVG radial gauge for composite SLACR score (0–5 scale).
 * Color bands: < 2 = green (Low Risk), 2–3.5 = amber (Moderate), > 3.5 = red (High).
 */

interface Props {
  score: number | null | undefined
  rating?: string | null
  size?: number
}

function scoreToColor(score: number): string {
  if (score < 2.0) return '#24a148'  // green — Low Risk
  if (score < 3.5) return '#0f62fe'  // blue — Moderate Risk
  if (score < 4.5) return '#f1c21b'  // amber — Elevated Risk
  return '#da1e28'                    // red — High / Decline
}

export default function RiskScoreGauge({ score, rating, size = 160 }: Props) {
  const cx = size / 2
  const cy = size / 2
  const r  = size * 0.36
  const strokeW = size * 0.1

  // Gauge spans 210° (from -210° start = 7 o'clock), going clockwise
  const startAngle = 210   // degrees from right-horizontal
  const sweepTotal = 300   // total arc
  const maxScore   = 5

  function polarToXY(angleDeg: number, radius: number) {
    const rad = ((angleDeg - 90) * Math.PI) / 180
    return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) }
  }

  function arcPath(startDeg: number, endDeg: number, radius: number, sw: number) {
    const s = polarToXY(startDeg, radius)
    const e = polarToXY(endDeg, radius)
    const largeArc = endDeg - startDeg > 180 ? 1 : 0
    return `M ${s.x} ${s.y} A ${radius} ${radius} 0 ${largeArc} 1 ${e.x} ${e.y}`
  }

  const trackStart = -startAngle + 90   // in SVG coordinate
  const trackEnd   = trackStart + sweepTotal

  // Map score 0–5 to angle sweep
  const fillAngle  = score != null
    ? Math.min(Math.max(score / maxScore, 0), 1) * sweepTotal
    : 0
  const fillEnd    = trackStart + fillAngle

  const color = score != null ? scoreToColor(score) : '#e0e0e0'

  // Band label positions
  const bands = [
    { label: 'Low',   deg: trackStart + sweepTotal * 0.08 },
    { label: 'Mod',   deg: trackStart + sweepTotal * 0.38 },
    { label: 'High',  deg: trackStart + sweepTotal * 0.78 },
  ]

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size * 0.78} viewBox={`0 0 ${size} ${size}`} style={{ overflow: 'visible' }}>
        {/* Track (grey background arc) */}
        <path
          d={arcPath(trackStart, trackEnd, r, strokeW)}
          fill="none"
          stroke="#e0e0e0"
          strokeWidth={strokeW}
          strokeLinecap="round"
        />
        {/* Fill arc */}
        {score != null && score > 0 && (
          <path
            d={arcPath(trackStart, fillEnd, r, strokeW)}
            fill="none"
            stroke={color}
            strokeWidth={strokeW}
            strokeLinecap="round"
          />
        )}
        {/* Center score text */}
        <text
          x={cx}
          y={cy + 6}
          textAnchor="middle"
          fontSize={size * 0.18}
          fontWeight={700}
          fill={score != null ? color : '#a8a8a8'}
        >
          {score != null ? score.toFixed(2) : '—'}
        </text>
        <text
          x={cx}
          y={cy + size * 0.14}
          textAnchor="middle"
          fontSize={size * 0.07}
          fill="#8d8d8d"
        >
          / 5.00
        </text>
      </svg>
      {rating && (
        <p className="text-xs font-semibold mt-1" style={{ color }}>
          {rating}
        </p>
      )}
    </div>
  )
}
