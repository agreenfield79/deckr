import MarkdownViewer from '../editor/MarkdownViewer'

// ---------------------------------------------------------------------------
// DeckrSections — exported so DeckrTab can import and build the typed object.
// New format (6 sections): §4 partnershipValue, §5 loanStructure (3-col table), §6 projections prose.
// Legacy format (5 sections): partnershipValue falls back to abilityToRepay names; biddingInstructions
//   kept for header contact extraction on old files.
// ---------------------------------------------------------------------------

export interface DeckrSections {
  header: string               // ## 1. Header
  companyOverview: string      // ## 2. Company Overview & History
  performance: string          // ## 3. Performance Summary
  partnershipValue: string     // ## 4. Partnership Value (replaces Ability to Repay)
  loanStructure: string        // ## 5. Proposed Loan Structure (3-col table: Term | Bank Terms | Proposed)
  biddingInstructions: string  // legacy — kept for header contact extraction on old files
  projectionsText?: string     // ## 6. Projections prose — retained for possible future use
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

/**
 * Extract contact and date from the pipe-delimited Section 1 Header line.
 * Format: Name | Loan Type | Amount | Contact | Date
 */
function parseBiddingInfo(header: string): { contact: string; date: string; subCaption: string } {
  const lines = header.split('\n').map((l) => l.trim()).filter(Boolean)
  const firstLine = lines[0] ?? ''
  const subCaption = lines.slice(1).join(' ').replace(/\*\*/g, '').trim()
  const pipes = firstLine.split('|').map((s) => s.trim())
  return {
    contact:    pipes[3] ?? '',
    date:       pipes[4] ?? '',
    subCaption,
  }
}

/**
 * Render Performance Summary splitting the markdown table from any trailing
 * prose. The prose is rendered as a full-width paragraph so it does not
 * inherit the table's column layout.
 */
function PerformanceContent({ content }: { content: string }) {
  const lines = content.split('\n')
  const tableLines: string[] = []
  const proseLines: string[] = []
  let passedTable = false

  for (const line of lines) {
    const trimmed = line.trim()
    const isTableLine = trimmed.startsWith('|') || /^\|[-\s|:]+\|$/.test(trimmed)
    if (!passedTable && isTableLine) {
      tableLines.push(line)
    } else if (tableLines.length > 0 && !isTableLine) {
      passedTable = true
      proseLines.push(line)
    } else if (passedTable) {
      proseLines.push(line)
    } else {
      proseLines.push(line)
    }
  }

  const tableContent = tableLines.join('\n').trim()
  const proseContent = proseLines.join('\n').trim()

  return (
    <div style={{ width: '100%' }}>
      {tableContent && <MarkdownViewer content={tableContent} textSize="10px" />}
      {proseContent && (
        <p style={{
          fontSize: '10px',
          color: '#525252',
          lineHeight: 1.45,
          margin: tableContent ? '6px 0 0' : '0',
          display: 'block',
          width: '100%',
        }}>
          {proseContent.replace(/\*\*/g, '')}
        </p>
      )}
    </div>
  )
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
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Two-column table (Term | Proposed) for the Proposed Loan Structure panel.
 * Flat — no group headers, no separators. All rows render in one continuous sequence.
 */
function LoanStructureTable({ rows }: { rows: LoanRow[] }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <tbody>
        {rows.map((row) => {
          const displayValue = /collateral/i.test(row.label) ? cleanCollateral(row.value) : row.value
          return (
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
            </tr>
          )
        })}
      </tbody>
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

  // Parse bidding info from Section 1 Header for the Bidding Instructions card
  const biddingInfo = parseBiddingInfo(sections.header)

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
              Loan Prospectus
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
              ? <PerformanceContent content={sections.performance} />
              : PENDING}
          </Panel>

          <Panel title="Partnership Value" accentColor="#ff832b">
            {sections.partnershipValue
              ? <MarkdownViewer content={sections.partnershipValue} textSize="10px" />
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
          } as React.CSSProperties}>
            <h2 style={{
              fontSize: '11px',
              fontWeight: 700,
              color: '#0043ce',
              margin: '0 0 2px',
              paddingBottom: '4px',
              borderBottom: '1px solid #c9deff',
            }}>
              Proposed Loan Structure
            </h2>
            {loanRows.length > 0
              ? <LoanStructureTable rows={loanRows} />
              : PENDING}
          </div>

          {/* Bidding Instructions — pulled from Section 1 Header metadata */}
          {(biddingInfo.contact || biddingInfo.date) && (
            <div style={{
              borderRadius: '6px',
              border: '1px solid #e0e0e0',
              borderLeft: '4px solid #6f6f6f',
              backgroundColor: '#f4f4f4',
              padding: '10px',
            }}>
              <h2 style={{
                fontSize: '11px',
                fontWeight: 700,
                color: '#161616',
                margin: '0 0 6px',
                paddingBottom: '4px',
                borderBottom: '1px solid #e0e0e0',
              }}>
                Bidding Instructions
              </h2>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <tbody>
                  {biddingInfo.contact && (
                    <tr>
                      <td style={{ fontSize: '8px', fontWeight: 600, color: '#525252', textTransform: 'uppercase', letterSpacing: '0.04em', padding: '3px 6px', width: '40%', verticalAlign: 'top', borderBottom: '1px solid #dde1e7' }}>
                        Submit Proposals To
                      </td>
                      <td style={{ fontSize: '10px', color: '#161616', padding: '3px 6px', verticalAlign: 'top', borderBottom: '1px solid #dde1e7' }}>
                        {biddingInfo.contact}
                      </td>
                    </tr>
                  )}
                  {biddingInfo.date && (
                    <tr>
                      <td style={{ fontSize: '8px', fontWeight: 600, color: '#525252', textTransform: 'uppercase', letterSpacing: '0.04em', padding: '3px 6px', verticalAlign: 'top', borderBottom: '1px solid #dde1e7' }}>
                        Date Prepared
                      </td>
                      <td style={{ fontSize: '10px', color: '#161616', padding: '3px 6px', verticalAlign: 'top', borderBottom: '1px solid #dde1e7' }}>
                        {biddingInfo.date}
                      </td>
                    </tr>
                  )}
                  <tr>
                    <td style={{ fontSize: '8px', fontWeight: 600, color: '#525252', textTransform: 'uppercase', letterSpacing: '0.04em', padding: '3px 6px', verticalAlign: 'top', borderBottom: '1px solid #dde1e7' }}>
                      Format
                    </td>
                    <td style={{ fontSize: '10px', color: '#161616', padding: '3px 6px', verticalAlign: 'top', borderBottom: '1px solid #dde1e7' }}>
                      Indicative term sheet preferred
                    </td>
                  </tr>
                  <tr>
                    <td style={{ fontSize: '8px', fontWeight: 600, color: '#525252', textTransform: 'uppercase', letterSpacing: '0.04em', padding: '3px 6px', verticalAlign: 'top' }}>
                      Confidentiality
                    </td>
                    <td style={{ fontSize: '10px', color: '#161616', padding: '3px 6px', verticalAlign: 'top' }}>
                      {biddingInfo.subCaption || 'For prospective lender use only'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}

        </div>
      </div>

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
