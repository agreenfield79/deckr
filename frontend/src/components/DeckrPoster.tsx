import MarkdownViewer from '../editor/MarkdownViewer'
import { DscrProjectionChart, LeverageProjectionChart } from '../charts/ProjectionsChart'
import type { ProjectionsOutput } from '../api/projections'

// ---------------------------------------------------------------------------
// DeckrSections — exported so DeckrTab can import and build the typed object.
// New format (6 sections): loanStructure = Section 5, biddingInstructions = Section 6.
// Legacy format (5 sections): loanStructure = '', biddingInstructions holds everything.
// ---------------------------------------------------------------------------

export interface DeckrSections {
  header: string               // ## 1. Header
  companyOverview: string      // ## 2. Company Overview & History
  performance: string          // ## 3. Performance Summary
  abilityToRepay: string       // ## 4. Credit Rationale (legacy: Ability to Repay)
  loanStructure: string        // ## 5. Loan Structure (markdown table: Term | Memo | Proposed)
  biddingInstructions: string  // ## 6. Bidding Instructions (process/contact)
  projections?: ProjectionsOutput | null  // from GET /api/projections/output — optional
  projectionsText?: string     // ## 7. Projections prose from deckr.md — optional
  raw: string                  // full original markdown — List View fallback
  hasStructure: boolean        // true when ≥3 named sections parsed
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface Props {
  sections: DeckrSections
}

// ---------------------------------------------------------------------------
// Loan-field extraction helpers
// ---------------------------------------------------------------------------

/**
 * Parse a labeled field from agent prose.
 * Handles both "Label: value" and "**Label:** value" (markdown bold).
 * Captures until the next "Word:" label boundary or paragraph break.
 */
function extractLabel(text: string, ...labels: string[]): string {
  const STOP =
    'Structure|Rate|Repayment|Collateral|Guaranty|Target\\s*[Cc]lose|Contact|' +
    'Process|Document|Submission|Next\\s*Steps?|Questions?'
  for (const label of labels) {
    const esc = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const re = new RegExp(
      `\\*{0,2}${esc}\\*{0,2}\\s*:\\s*([\\s\\S]*?)(?=\\n?\\*{0,2}(?:${STOP})\\*{0,2}\\s*:|\\n\\n|$)`,
      'i',
    )
    const m = text.match(re)
    if (m) return m[1].trim().replace(/\*\*/g, '').replace(/\s+/g, ' ')
  }
  return '—'
}

/** Parse pipe-delimited Section 1 header: Name | Loan Type | Amount | ... */
function parseHeaderPipes(header: string) {
  const clean = header.replace(/\*\*/g, '').replace(/[\[\]]/g, '')
  const pipes = clean.split('|').map((s) => s.trim())
  return {
    name:       pipes[0] ?? '',
    loanType:   pipes[1] ?? '',
    loanAmount: pipes[2] ?? '',
  }
}

/** Fallback regex for dollar amount when header is not pipe-delimited */
function extractAmountFallback(text: string): string {
  const m = text.match(/\$[\d,.]+(?:\s*(?:million|billion|[MBK]))?/i)
  return m ? m[0] : '—'
}

/**
 * Build the header display line: Name | Loan Type | Amount | Contact: [...]
 * Replaces the old stripPurposeFromHeader — drops purpose/date, adds contact info.
 * URL shortening: strips https:// for display; full URL preserved in deckr.md.
 */
function buildHeaderLine(header: string, biddingInstructions: string): string {
  const pipes = parseHeaderPipes(header)
  const name      = pipes.name
  const loanType  = pipes.loanType
  const amount    = pipes.loanAmount || extractAmountFallback(header)

  // Extract Contact from Section 6 (new format) or fall back to the header itself
  const contact = extractLabel(biddingInstructions, 'Contact')

  let contactDisplay = ''
  if (contact && contact !== '—') {
    // Strip protocol for brevity
    contactDisplay = contact.replace(/https?:\/\//gi, '').replace(/\/$/, '')
    // If overflow-prone (>80 chars after protocol strip), truncate after email
    if (contactDisplay.length > 80) {
      const emailEnd = contactDisplay.search(/,\s*[^\s,@]+\.[^\s,]{2,}(?:\/[^\s,]*)?$/)
      if (emailEnd > 0) {
        contactDisplay = contactDisplay.slice(0, emailEnd) + ', DD Room ↗'
      }
    }
  }

  return [name, loanType, amount, contactDisplay ? `Contact: ${contactDisplay}` : ''].filter(Boolean).join(' | ')
}

/**
 * Remove dollar-amount annotations, LTV figures, and covenant thresholds from
 * a collateral description. Keeps the asset-class description only.
 * e.g. "first-lien on cash (~$62B); LTV 13% (well below 60%)" → "first-lien on cash"
 */
function cleanCollateral(value: string): string {
  if (!value || value === '—') return value
  return value
    .replace(/\s*\(~?\$[^)]+\)/g, '')
    .replace(/\s*\(~?[\d.]+\s*%[^)]*\)/g, '')
    .replace(/[,;]?\s*resulting\s+in\s+an?\s+LTV[^.;]*/gi, '')
    .replace(/[,;]?\s*\(well\s+below[^)]+\)/gi, '')
    .replace(/[,;]?\s*LTV\s+(?:of\s+)?~?[\d.]+\s*%[^,;.]*/gi, '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[.,;]+$/, '')
}

// ---------------------------------------------------------------------------
// Loan Structure row parsing — new primary path (markdown table)
// ---------------------------------------------------------------------------

interface LoanRow { label: string; value: string }

/**
 * Parse a markdown table `| Term | Memo | Proposed |` from Section 5 of deckr.md.
 * Returns only (Term, Proposed) pairs for rendering.
 * Falls back to an empty array if no table is detected — caller uses parseLoanFieldsFallback().
 */
function parseLoanStructureRows(loanStructure: string): LoanRow[] {
  if (!loanStructure) return []

  // Detect markdown table by separator row: |---|---|---|
  if (!/\|[-\s|]+\|/.test(loanStructure)) return []

  const lines = loanStructure.split('\n').map((l) => l.trim()).filter(Boolean)

  // Find the header row that names columns
  const headerIdx = lines.findIndex((l) => /\|.*term.*\|.*proposed/i.test(l))
  if (headerIdx === -1) return []

  // Identify "Proposed" column index (skip empty leading split artifact)
  const headerCells = lines[headerIdx].split('|').map((c) => c.trim()).filter(Boolean)
  const proposedIdx = headerCells.findIndex((c) => /proposed/i.test(c))
  if (proposedIdx === -1) return []

  // Absolute column index in the split-by-pipe array (account for leading |)
  // When a row starts with |, split('|') produces ['', cell1, cell2, ...]
  // headerCells is already filtered (no empty leading), so proposedIdx maps to
  // the (proposedIdx+1)th non-empty cell. We reparse each row properly.
  const rows: LoanRow[] = []

  for (let i = headerIdx + 1; i < lines.length; i++) {
    const line = lines[i]
    // Skip separator rows
    if (/^\|[-\s|:]+\|$/.test(line)) continue

    const cells = line.split('|').map((c) => c.trim())
    // Leading | produces cells[0] === '' — shift all by 1
    const offset = cells[0] === '' ? 1 : 0
    const label = (cells[offset] ?? '').replace(/\*\*/g, '').trim()
    const value = (cells[offset + proposedIdx] ?? '').replace(/\*\*/g, '').trim()

    if (!label || /^-+$/.test(label)) continue
    rows.push({ label, value: value || '—' })
  }

  return rows
}

// ---------------------------------------------------------------------------
// Legacy fallback — labeled-field format (pre-table agent output)
// ---------------------------------------------------------------------------

function extractRateFromStructure(s: string): string {
  const m = s.match(
    /\b(fixed[- ]rate|floating[- ]rate|fixed|floating|variable|prime|SOFR|LIBOR)\b[^,;.]*(?:[\+\-]\s*[\d.]+\s*(?:bps|bp|%))?[^,;.]*/i,
  )
  return m ? m[0].trim().replace(/^[,\s]+/, '') : '—'
}

function extractRepaymentFromStructure(s: string): string {
  const m = s.match(
    /(?:(?:monthly|quarterly|annual|semi-?annual|biannual)\s+)?(?:interest[- ]only|P&I|principal\s+and\s+interest|amortiz)[^.]+/i,
  )
  return m ? m[0].trim() : '—'
}

function extractTermFromStructure(s: string): string {
  const primary = s.match(
    /(\d+)\s*-?\s*(year|month)s?\s+(?:senior|junior|term|bridge|secured|unsecured|construction|equipment)/i,
  )
  if (primary) return `${primary[1]}-${primary[2].toLowerCase()}`
  const fallback = s.match(/\b(\d+)\s*-?\s*(year|month)s?\b/i)
  return fallback ? `${fallback[1]}-${fallback[2].toLowerCase()}` : '—'
}

function parseLoanFieldsFallback(sections: DeckrSections): LoanRow[] {
  const { header, loanStructure, biddingInstructions } = sections
  const pipes = parseHeaderPipes(header)
  const src = loanStructure || biddingInstructions

  const structureField  = extractLabel(src, 'Structure')
  const rateField       = extractLabel(src, 'Rate')
  const repaymentField  = extractLabel(src, 'Repayment')
  const collateralField = extractLabel(src, 'Collateral')
  const guarantyField   = extractLabel(src, 'Guaranty')
  const closeField      = extractLabel(src, 'Target Close', 'Target close')

  const term       = extractTermFromStructure(structureField !== '—' ? structureField : src)
  const rate       = rateField !== '—'      ? rateField      : extractRateFromStructure(structureField !== '—' ? structureField : src)
  const repayment  = repaymentField !== '—' ? repaymentField : extractRepaymentFromStructure(structureField !== '—' ? structureField : src)
  const loanType   = pipes.loanType || (structureField !== '—' ? structureField.split(',')[0].trim() : '—')
  const loanAmount = pipes.loanAmount || extractAmountFallback(header)

  return [
    { label: 'Loan Amount',  value: loanAmount },
    { label: 'Structure',    value: loanType },
    { label: 'Term',         value: term },
    { label: 'Rate',         value: rate },
    { label: 'Repayment',    value: repayment },
    { label: 'Collateral',   value: cleanCollateral(collateralField) },
    { label: 'Guaranty',     value: guarantyField },
    { label: 'Target Close', value: closeField },
  ]
}

// ---------------------------------------------------------------------------
// Group separator logic — matches by label name, not row position
// ---------------------------------------------------------------------------

type RowGroup = 'LOAN TERMS' | 'COVENANTS & COMPLIANCE' | 'CONDITIONS' | null

function getRowGroup(label: string): RowGroup {
  const l = label.toLowerCase()
  // Use \b word-boundary so "prepayment" does NOT match \brepayment\b
  if (/structure|\brate\b|\brepayment\b|collateral|guaranty|target\s*close/.test(l)) return 'LOAN TERMS'
  if (/covenant|reporting|prepayment/.test(l)) return 'COVENANTS & COMPLIANCE'
  if (/condition/.test(l)) return 'CONDITIONS'
  return null
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Two-column table (Term | Proposed) for the Loan Structure panel.
 * Group labels appear as full-width section headers within the table.
 */
function LoanStructureTable({ rows }: { rows: LoanRow[] }) {
  const tableRows: React.ReactNode[] = []
  let currentGroup: RowGroup = null

  for (const row of rows) {
    const group = getRowGroup(row.label)
    if (group && group !== currentGroup) {
      currentGroup = group
        tableRows.push(
        <tr key={`sep-${group}`}>
          <td
            colSpan={2}
            style={{
              padding: '3px 6px 2px',
              fontSize: '7px',
              fontWeight: 700,
              color: '#0043ce',
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
              textAlign: 'center',
              backgroundColor: '#dbeafe',
              borderTop: tableRows.length > 0 ? '1px solid #c9deff' : undefined,
              borderBottom: '1px solid #c9deff',
            }}
          >
            {group}
          </td>
        </tr>,
      )
    }

    const displayValue = /collateral/i.test(row.label) ? cleanCollateral(row.value) : row.value
    tableRows.push(
      <tr key={row.label}>
        <td style={{
          padding: '3px 6px',
          fontSize: '8px',
          fontWeight: 600,
          color: '#525252',
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          verticalAlign: 'top',
          width: '28%',
          lineHeight: 1.3,
          borderBottom: '1px solid #dde1e7',
        }}>
          {row.label}
        </td>
        <td style={{
          padding: '3px 6px',
          fontSize: '10px',
          fontWeight: 400,
          color: '#161616',
          verticalAlign: 'top',
          lineHeight: 1.35,
          borderBottom: '1px solid #dde1e7',
        }}>
          {displayValue}
        </td>
      </tr>,
    )
  }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <tbody>{tableRows}</tbody>
    </table>
  )
}

interface PanelProps {
  title: string
  accentColor: string
  bgColor?: string
  borderColor?: string
  titleColor?: string
  children: React.ReactNode
}

function Panel({ title, accentColor, bgColor = '#ffffff', borderColor = '#e0e0e0', titleColor = '#161616', children }: PanelProps) {
  return (
    <div style={{
      borderRadius: '6px',
      border: `1px solid ${borderColor}`,
      borderLeft: `4px solid ${accentColor}`,
      backgroundColor: bgColor,
      padding: '10px',
      display: 'flex',
      flexDirection: 'column',
      gap: '4px',
    }}>
      <h2 style={{
        fontSize: '11px',
        fontWeight: 700,
        color: titleColor,
        margin: '0 0 1px',
        paddingBottom: '4px',
        borderBottom: `1px solid ${borderColor}`,
      }}>
        {title}
      </h2>
      {children}
    </div>
  )
}

const PENDING = (
  <p style={{ fontSize: '12px', color: '#a8a8a8', fontStyle: 'italic', margin: 0 }}>
    [Section pending — run Deckr Agent to generate]
  </p>
)

// ---------------------------------------------------------------------------
// DeckrPoster — main component
// ---------------------------------------------------------------------------

export default function DeckrPoster({ sections }: Props) {
  // Parse Loan Structure rows — prefer new markdown table; fall back to labeled fields
  const tableRows = parseLoanStructureRows(sections.loanStructure)
  const loanRows: LoanRow[] = tableRows.length > 0
    ? tableRows
    : parseLoanFieldsFallback(sections)

  // Build header display line (Name | Loan Type | Amount | Contact: ...)
  const headerLine = buildHeaderLine(sections.header, sections.biddingInstructions)

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', backgroundColor: 'white', border: '1px solid #e0e0e0' }}>

      {/* ------------------------------------------------------------------ */}
      {/* Full-width IBM blue header                                          */}
      {/* ------------------------------------------------------------------ */}
      <div style={{
        backgroundColor: '#0f62fe',
        padding: '12px 22px',
        printColorAdjust: 'exact',
        WebkitPrintColorAdjust: 'exact',
      } as React.CSSProperties}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: '8px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#a6c8ff', marginBottom: '3px' }}>
              Borrower Package · Confidential
            </div>
            <h1 style={{ fontSize: '18px', fontWeight: 700, color: 'white', margin: 0, lineHeight: 1.2 }}>
              Deal Sheet
            </h1>
          </div>
          <div style={{ fontSize: '8px', color: '#a6c8ff', textAlign: 'right', opacity: 0.8 }}>
            Powered by Deckr · IBM watsonx
          </div>
        </div>

        {/* Section 1 header line — Name | Loan Type | Amount | Contact */}
        {sections.header && (
          <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid rgba(166,200,255,0.4)' }}>
            <p style={{ fontSize: '11px', color: 'white', margin: 0, lineHeight: 1.4 }}>
              {headerLine}
            </p>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* 2-column poster grid                                                */}
      {/* ------------------------------------------------------------------ */}
      <div className="poster-grid-inner" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', padding: '10px' }}>

        {/* LEFT COLUMN — Company Overview + Performance Summary + Credit Rationale */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>

          <Panel title="Company Overview & History" accentColor="#0f62fe">
            {sections.companyOverview
              ? <MarkdownViewer content={sections.companyOverview} textSize="10px" />
              : PENDING}
          </Panel>

          <Panel title="Performance Summary" accentColor="#198038">
            {sections.performance
              ? <MarkdownViewer content={sections.performance} textSize="10px" />
              : PENDING}
          </Panel>

          <Panel title="Credit Rationale" accentColor="#ff832b">
            {sections.abilityToRepay
              ? <MarkdownViewer content={sections.abilityToRepay} textSize="10px" />
              : PENDING}
          </Panel>

        </div>

        {/* RIGHT COLUMN — Loan Structure (full height) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>

          {/* Loan Structure accent panel */}
          <div style={{
            borderRadius: '6px',
            border: '1px solid #c9deff',
            borderLeft: '4px solid #0043ce',
            backgroundColor: '#edf5ff',
            padding: '10px',
            printColorAdjust: 'exact',
            WebkitPrintColorAdjust: 'exact',
            flex: 1,
          } as React.CSSProperties}>
            <h2 style={{
              fontSize: '11px',
              fontWeight: 700,
              color: '#0043ce',
              margin: '0 0 2px',
              paddingBottom: '4px',
              borderBottom: '1px solid #c9deff',
            }}>
              Loan Structure
            </h2>
            {loanRows.length > 0
              ? <LoanStructureTable rows={loanRows} />
              : PENDING}
          </div>

        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Full-width Projections Banner — below 2-col grid, above footer    */}
      {/* ------------------------------------------------------------------ */}
      {sections.projections && (
        <div style={{
          borderTop: '1px solid #e0e0e0',
          padding: '8px 12px',
          printColorAdjust: 'exact',
          WebkitPrintColorAdjust: 'exact',
        } as React.CSSProperties}>
          {/* Banner header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <span style={{
              fontSize: '8px',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: '#ffffff',
              backgroundColor: '#ff832b',
              padding: '2px 6px',
              borderRadius: '2px',
            }}>
              3-Year Projections
            </span>
            <span style={{ fontSize: '9px', color: '#6f6f6f' }}>
              Base · Upside · Stress · Covenant thresholds: DSCR ≥ 1.25x, Debt/EBITDA ≤ 4.0x
            </span>
          </div>
          {/* Optional prose from deckr.md Section 7 */}
          {sections.projectionsText && (
            <p style={{ fontSize: '9px', color: '#525252', marginBottom: '6px', lineHeight: 1.4 }}>
              {sections.projectionsText.replace(/###.*\n/g, '').replace(/\*\*/g, '').trim().split('\n')[0]}
            </p>
          )}
          {/* Side-by-side compact charts */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
            <DscrProjectionChart data={sections.projections} compact />
            <LeverageProjectionChart data={sections.projections} compact />
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Full-width footer                                                   */}
      {/* ------------------------------------------------------------------ */}
      <div style={{ padding: '5px 22px', borderTop: '1px solid #ffd9b5' }}>
        <p style={{ fontSize: '8px', color: '#a8a8a8', textAlign: 'center', fontStyle: 'italic', margin: 0 }}>
          Generated by Deckr · Powered by IBM watsonx · This document is prepared for the borrower's use in approaching prospective lenders.
        </p>
      </div>

    </div>
  )
}
