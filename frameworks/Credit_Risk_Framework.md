# Credit Risk Framework

## Overview

The SLACR framework evaluates borrower credit risk across five core dimensions:

* **S — Strength**
* **L — Leverage**
* **A — Ability to Repay**
* **C — Collateral**
* **R — Risk Factors**

Each dimension is scored from **1 (Strong) to 5 (High Risk)** and weighted to produce a composite risk rating.

Lower score = lower risk.

---

# Scoring Scale

| Score | Description |
| ----- | ----------- |
| 1     | Strong      |
| 2     | Good        |
| 3     | Acceptable  |
| 4     | Weak        |
| 5     | High Risk   |

---

# Category Weights

| Category         | Weight |
| ---------------- | ------ |
| Strength         | 20%    |
| Leverage         | 20%    |
| Ability to Repay | 25%    |
| Collateral       | 15%    |
| Risk Factors     | 20%    |

Total = 100%

---

# Composite Score Formula

SLACR Score:

```
(S × 0.20) +
(L × 0.20) +
(A × 0.25) +
(C × 0.15) +
(R × 0.20)
```

Where:

S = Strength score
L = Leverage score
A = Ability to Repay score
C = Collateral score
R = Risk Factors score

---

# Risk Rating Bands

| Score       | Rating        | Interpretation |
| ----------- | ------------- | -------------- |
| 1.00 – 1.75 | Low Risk      | Strong credit  |
| 1.76 – 2.50 | Moderate Risk | Acceptable     |
| 2.51 – 3.25 | Elevated Risk | Monitor        |
| 3.26 – 4.00 | High Risk     | Weak           |
| 4.01 – 5.00 | Decline       | Unacceptable   |

---

# S — Strength

## Purpose

Evaluate overall borrower financial and business strength.

## Considerations

Revenue scale
Revenue stability
Profitability
Growth trend
Market position
Customer diversification
Competitive advantages
Years in business
Management experience

## Scoring Matrix

| Score | Criteria                                   |
| ----- | ------------------------------------------ |
| 1     | Large, stable, diversified borrower        |
| 2     | Strong performance, moderate concentration |
| 3     | Average borrower, moderate volatility      |
| 4     | Small borrower, inconsistent performance   |
| 5     | Weak or declining business                 |

---

# L — Leverage

## Purpose

Evaluate capital structure and debt burden.

## Metrics

Debt / EBITDA
Debt / Tangible Net Worth
Senior leverage
Total leverage
Pro forma leverage

## Scoring Matrix

| Score | Debt / EBITDA |
| ----- | ------------- |
| 1     | < 2.0x        |
| 2     | 2.0x – 3.0x   |
| 3     | 3.0x – 4.0x   |
| 4     | 4.0x – 5.0x   |
| 5     | > 5.0x        |

---

# A — Ability to Repay

## Purpose

Evaluate repayment capacity.

## Metrics

DSCR
Fixed charge coverage
Free cash flow
EBITDA stability
Cash flow volatility

## Scoring Matrix

| Score | DSCR          |
| ----- | ------------- |
| 1     | > 2.00x       |
| 2     | 1.50x – 2.00x |
| 3     | 1.25x – 1.50x |
| 4     | 1.00x – 1.25x |
| 5     | < 1.00x       |

---

# C — Collateral

## Purpose

Evaluate collateral support.

## Considerations

Collateral type
Liquidation value
Loan-to-value
Asset quality
Marketability
Lien position
Appraisal support

## Scoring Matrix

| Score | LTV       |
| ----- | --------- |
| 1     | < 50%     |
| 2     | 50% – 65% |
| 3     | 65% – 80% |
| 4     | 80% – 95% |
| 5     | > 95%     |

---

# R — Risk Factors

## Purpose

Evaluate qualitative risks.

## Considerations

Customer concentration
Supplier concentration
Industry cyclicality
Management depth
Key person dependency
Economic sensitivity
Regulatory risk
Litigation risk
Financial reporting quality

## Scoring Matrix

| Score | Criteria                     |
| ----- | ---------------------------- |
| 1     | Minimal qualitative risk     |
| 2     | Minor risks                  |
| 3     | Moderate risks               |
| 4     | Elevated risks               |
| 5     | Significant structural risks |

---

# SLACR Worksheet

## Strength

Score:
Notes:

## Leverage

Score:
Notes:

## Ability to Repay

Score:
Notes:

## Collateral

Score:
Notes:

## Risk Factors

Score:
Notes:

---

# Composite Score Calculation

```
SLACR =
(S × .20) +
(L × .20) +
(A × .25) +
(C × .15) +
(R × .20)
```

---

# Example

S = 2
L = 3
A = 2
C = 2
R = 3

```
SLACR =
(2×.20)+(3×.20)+(2×.25)+(2×.15)+(3×.20)
= 2.40
```

Rating:

Moderate Risk

---

# Credit Decision Guidance

| Rating    | Guidance                |
| --------- | ----------------------- |
| Low Risk  | Approve                 |
| Moderate  | Approve with conditions |
| Elevated  | Further review          |
| High Risk | Decline or restructure  |
| Decline   | Reject                  |

---

# Mitigants

Collateral coverage
Guarantor support
Covenants
Pricing
Amortization
Borrowing base
Cash sweep

---

# AI Output Schema

```json
{
  "slacr": {
    "strength": {
      "score": 0,
      "notes": ""
    },
    "leverage": {
      "score": 0,
      "notes": ""
    },
    "ability_to_repay": {
      "score": 0,
      "notes": ""
    },
    "collateral": {
      "score": 0,
      "notes": ""
    },
    "risk_factors": {
      "score": 0,
      "notes": ""
    }
  },
  "weighted_score": 0,
  "rating": "",
  "decision": "",
  "mitigants": []
}
```

---

# Integration Notes

This framework is used by watsonxai Agent

---

# UI Mapping (Future)

Each category becomes:

Slider 1–5
Notes field
Auto score calculation
Risk rating auto-generated
