---
name: School Finance Design System
description: High-precision financial console and tuition billing management interface for schools with multi-campus governance.
colors:
  primary: "#0f172a"
  primary-hover: "#1e293b"
  primary-subtle: "#f1f5f9"
  canvas: "#f8fafc"
  surface: "#ffffff"
  border-subtle: "#e2e8f0"
  border-strong: "#cbd5e1"
  text-primary: "#0f172a"
  text-secondary: "#475569"
  text-muted: "#64748b"
  text-inverse: "#f8fafc"
  text-inverse-muted: "#94a3b8"
  emerald-base: "#059669"
  emerald-subtle: "#ecfdf5"
  emerald-border: "#a7f3d0"
  emerald-text: "#065f46"
  amber-base: "#d97706"
  amber-subtle: "#fffbeb"
  amber-border: "#fde68a"
  amber-text: "#92400e"
  rose-base: "#e11d48"
  rose-subtle: "#fff1f2"
  rose-border: "#fecdd3"
  rose-text: "#9f1239"
  indigo-base: "#4f46e5"
  indigo-subtle: "#eef2ff"
  indigo-border: "#c7d2fe"
  indigo-text: "#3730a3"
typography:
  display:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "clamp(1.5rem, 3vw, 2rem)"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.5
  tabular-money:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.625rem"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.04em"
rounded:
  sm: "6px"
  md: "10px"
  lg: "14px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.text-inverse}"
    rounded: "{rounded.sm}"
    padding: "8px 14px"
    height: "34px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    padding: "8px 14px"
    height: "34px"
  kpi-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "18px 20px"
---

# School Finance Design System

## Overview

School Finance is a calm, high-precision financial management application designed for school directors, campus administrators, finance officers, and shareholder stakeholders. 

The interface emphasizes:
- **Financial Truth & Legibility**: Numbers carry the hierarchy. Integer cents arithmetic, tabular numerals, and explicit collection percentages ensure zero ambiguity.
- **Tenant Scope Clarity**: School umbrella vs. Campus branch contexts are immediately obvious at every level of navigation.
- **Speed of Daily Operation**: Fast fee collection, immediate receipt generation, and rapid arrears triage with zero cognitive overhead.

---

## Colors

The palette operates on a **Calm Slate SaaS** foundation with semantic functional accents.

### Core Canvas & Neutrals
- **Canvas Background** (`#f8fafc` / `slate-50`): The base page ground for all views.
- **Surface & Cards** (`#ffffff`): Crisp foreground surfaces for data containers, modals, and KPI cards.
- **Navigation Rail** (`#0f172a` / `slate-900`): Deep anchored sidebar providing clear grounding and role indication.
- **Micro-Borders** (`#e2e8f0` / `slate-200`): Hairline 1px dividers establishing container structure without visual clutter.
- **Primary Text** (`#0f172a` / `slate-900`): Maximum contrast for financial data, student names, and headlines.
- **Secondary / Muted Text** (`#64748b` / `slate-500`): Contextual metadata, table column headers, and helper descriptions.

### Functional Accents
- **Emerald** (Base `#059669`, Subtle `#ecfdf5`, Border `#a7f3d0`, Text `#065f46`):
  Used for collection percentages, positive cash positions, cleared fees, and primary success confirmation.
- **Amber** (Base `#d97706`, Subtle `#fffbeb`, Border `#fde68a`, Text `#92400e`):
  Used for outstanding arrears, overdue follow-up tags, and attention warnings.
- **Rose** (Base `#e11d48`, Subtle `#fff1f2`, Border `#fecdd3`, Text `#9f1239`):
  Used for severe overdue arrears balances, negative margins, and soft-archive destructive actions.
- **Indigo** (Base `#4f46e5`, Subtle `#eef2ff`, Border `#c7d2fe`, Text `#3730a3`):
  Used for fee credit rollovers, forward allocations, and informational badges.

---

## Typography

The design system uses **Inter** with tailored OpenType feature flags for maximum numerical and micro-copy readability.

### Type Scale
| Role | Size | Weight | Line Height | Letter Spacing | Use Case |
|---|---|---|---|---|---|
| **Display / Page Title** | `24px` | 700 (Bold) | 1.2 | `-0.03em` | Primary view header |
| **Headline / Card Title** | `14px`–`16px` | 700 (Bold) | 1.3 | `-0.01em` | Panel titles, campus names |
| **KPI Amount** | `26px` | 700 (Bold) | 1.1 | `-0.04em` | Tabular financial amounts |
| **Table Head / Micro Label**| `10px`–`11px` | 600 (Semibold)| 1.4 | `+0.05em` | Uppercase metric labels |
| **Body Default** | `13px` | 400 (Regular) | 1.5 | `normal` | General table text, form values |
| **Receipt Monospace** | `11px` | 400 (Regular) | 1.4 | `normal` | Printable payment receipts |

### Numerals Rule
All financial amounts, student counts, and percentages **MUST** enable tabular numbers:
```css
.num {
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}
```

---

## Layout

### App Shell
- **Grid Layout**: 2-column structure with fixed `240px` Navigation Rail on desktop and fluid `1fr` Workspace.
- **Workspace Bounds**: `max-width: 1280px` centered with `32px` gutter padding on desktop (`16px` on mobile).
- **Sticky Utilities**:
  - `56px` height topbar fixed to top with breadcrumb path, campus selector pill, and user profile avatar.
  - Sticky navigation rail with role indicator pinned to footer.

### Grid Systems
- **Executive Metric Row**: `grid-template-columns: repeat(4, 1fr)` on desktop, 2-column on tablet, single-column on mobile.
- **Campus Decision Deck**: `grid-template-columns: repeat(2, 1fr)` on desktop, single-column on mobile.

---

## Elevation & Depth

The design system relies on **tonal contrast and soft ambient shadows** rather than harsh directional drops:
- **Card Shadow (`--shadow-sm`)**: `0 1px 2px 0 rgba(15, 23, 42, 0.05)`
- **Interactive / Hover Shadow (`--shadow-md`)**: `0 4px 6px -1px rgba(15, 23, 42, 0.07), 0 2px 4px -2px rgba(15, 23, 42, 0.05)`
- **Modal / Floating Bar Shadow (`--shadow-lg`)**: `0 10px 15px -3px rgba(15, 23, 42, 0.08), 0 4px 6px -4px rgba(15, 23, 42, 0.03)`
- **Modal Backdrop**: `rgba(15, 23, 42, 0.45)` with `backdrop-filter: blur(2px)`.

---

## Shapes

- **Base Radius (`--radius-sm: 6px`)**: Buttons, inputs, table row highlights, and micro-tags.
- **Card Radius (`--radius-md: 10px`)**: Metric cards, content panels, and toast alerts.
- **Modal Radius (`--radius-lg: 14px`)**: Popovers, dialogs, and slide-overs.
- **Pill Radius (`--radius-full: 9999px`)**: Status badges, campus switcher pills, and floating action dock.

---

## Components

### 1. Buttons
- **Primary**: Background `#0f172a`, Text `#ffffff`, 1px solid `#0f172a`. Hover `#1e293b`.
- **Secondary**: Background `#ffffff`, Text `#0f172a`, 1px solid `#cbd5e1`. Hover `#f1f5f9`.
- **Emerald Accent**: Background `#059669`, Text `#ffffff`. Used for recording payments and clearing fee arrears.

### 2. Status Badges
Pill shape (`padding: 2px 8px`, `font-size: 10px`, semibold uppercase):
- Active: `.badge-emerald` (Green text on subtle green ground)
- Arrears / Urgent: `.badge-amber` (Amber text on subtle yellow ground)
- Archived / Neutral: `.badge-slate` (Slate text on subtle slate ground)

### 3. Collection Progress Bar
- Background track: `#e2e8f0` (`height: 7px`, rounded).
- Fill bar: `#059669` (`transform-origin: left`, smooth `transform: scaleX(...)` animation for performance without layout thrashing).

### 4. Data Ledger Table
- Headers: `#f1f5f9` background, uppercase `10px`/`11px` muted text, left-aligned (`amount-head` right-aligned).
- Rows: Clean `14px 16px` padding, bottom hairline rule (`#e2e8f0`), `#fafafa` on hover.
- Financial cells: Always right-aligned with bold tabular formatting.

### 5. Payment Modal & Allocation Simulator
- Compact 2-column input grid for student, amount, target billing month, and payment method.
- Live monospace receipt slip rendering student name, monthly rate, paid amount, and automatic credit rollover calculation.

---

## Do's and Don'ts

### Do:
- **DO** format all currency with the `money()` helper or `$X.00` format with tabular numerals.
- **DO** clearly show when an account has rolled forward overpaid funds as credit.
- **DO** present school-wide totals alongside per-campus breakdowns so directors can drill down instantly.
- **DO** provide accessible keyboard navigation (`1`, `2`, `3`, `P`, `R`, `Esc`).
- **DO** use transform properties (`scaleX`) instead of layout properties (`width`) for progress transitions.

### Don't:
- **DON'T** use multi-color rainbow gradients or decorative 3D illustrations.
- **DON'T** use thick side-tab borders on alert cards.
- **DON'T** hide mutation controls with opacity alone; provide explicit read-only notices for Owner/Shareholder roles.
- **DON'T** perform financial arithmetic inside Jinja view templates; keep all billing derived from enrollment in service layers.
- **DON'T** invent artificial charges; maintain the derived expected-vs-paid billing model.
