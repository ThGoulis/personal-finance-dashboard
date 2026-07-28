# Technical Documentation — Financial Planner

## 1. Architecture Overview

**Type:** Static web application split into three files (`index.html`, `style.css`, `script.js`). No backend, no build process, no external runtime dependencies beyond Google Fonts (loaded via `@import`).

**Stack:** Vanilla HTML5, CSS3 (custom properties for theming), vanilla JavaScript (ES6+). No frameworks, no bundler.

**Rendering model:** Six panels (`#tabHub`, `#tabSalary`, `#tabBudget`, `#tabInvest`, `#tabMoto`, `#tabLoan`) toggled via inline `style.display`, managed by a `showTab(name)` function. All six panels exist in the DOM simultaneously; only one is visible at a time. `#tabHub` (the dashboard) is the default view on load.

**State management:** No formal state store. All state lives in the DOM (input field values) plus a small set of module-level `let` globals that cache the most recent computed results for cross-tab consumption (see §4.6).

---

## 2. File Structure

```
index.html
  - Meta tags: charset, viewport, title, description, OG/Twitter cards, Google verification
  - <link rel="stylesheet" href="style.css">
  - Letterhead (title, tagline, language toggle, date stamp)
  - Dismissible intro card (first-visit onboarding)
  - Toolbar (Reset to Defaults, Print Report)
  - Summary bar (mini live reference: net salary, savings, loan payment, unified balance + status pill)
  - Tab navigation (Hub icon + 5 text tabs)
  - Tab panels:
      Hub    -> 5 live summary cards (Salary, Budget, Investments, Vehicle, Loan),
               each a clickable shortcut into its own tab
      Salary -> net salary, bonuses, extra hours; branches into three
               employment-type modes (see Section 4.13)
      Budget -> personal budget, reserve fund
      Invest -> compound-interest calculator (its own tab, previously nested in Budget)
      Moto   -> vehicle expenses (fixed + operating), independent of loan status
      Loan   -> amortization, prepayment scenarios, debt-to-income indicator
  - Site-wide disclaimer footer + signature/license line
  - Hidden #printReport container (populated on demand)
  - <script src="script.js">

style.css
  - CSS custom properties (design tokens), base styles, component styles, responsive rules

script.js
  - TRANSLATIONS dictionary (el/en) + i18n apply/set/load functions
  - Currency formatting helpers (locale-aware)
  - Loan amortization engine (recompute, buildSchedule, monthlyPayment)
  - Prepayment scenario engine (computePrepayment)
  - Salary/tax engine (netFromGross, annualTax, effectiveTaxCredit, recomputeSalary)
  - Budget engine (recomputeBudget) incl. bonus-to-expense allocation, reserve fund,
    DTI indicator, summary bar updates
  - Investment calculator engine (recomputeInvestment)
  - Hub dashboard engine (updateHubCards) -- mirrors already-computed values into
    the dashboard cards; does not duplicate any calculation logic
  - Input validation/clamping (FIELD_BOUNDS)
  - Print report generator (builds a standalone HTML report on demand)
  - Init sequence (initial recompute calls, event listener wiring, showTab('hub'))

tests/qa_tests.py
  - Playwright-driven regression suite (see Section 9)

screenshots/
  - Reference images used in README.md
```

---

## 3. Design System

**Palette (CSS custom properties):** warm paper/ink ledger aesthetic — cream paper background with a faint ruled-line texture, dark teal ink for text and primary actions, brass/amber for secondary accents and warnings, red-ink for deductions/deficits.

**Typography:** Fraunces (serif, headings), IBM Plex Mono (monospace, labels/numbers/UI chrome), Inter (sans-serif, body text).

**Layout primitives:**
- `.card` — bordered content block, `min-width:0` to prevent grid/flex overflow
- `.grid` — two-column layout (1.1fr/1fr), collapses to one column ≤760px
- `.results` — 2-column grid for paired result boxes, collapses to one column ≤640px
- `.result-box.big` — spans all columns via `grid-column:1/-1` (not `1/3`, which would hard-code a 2-column assumption and break single-column grids)
- `.hub-grid` — 2-column grid of dashboard cards (`.hub-card`), one card (`.hub-card-wide`) spans full width via `grid-column:1/-1`
- `.tab-nav` (mobile) — 3-column **CSS Grid** (not flex-wrap): every button in the same row gets equal height automatically, avoiding the ragged look flex-wrap produces when one label wraps to two lines and its neighbors don't

**Responsive strategy:** one `@media (max-width:640px)` block handles mobile refinements without touching desktop rules. Grid children (`.grid`, `.results`, `.tab-nav` buttons) get `min-width:0` explicitly — without it, CSS Grid's default `min-width:auto` lets long content (especially English strings, which run longer than Greek, or single long Greek words with no space to wrap on, like "Προϋπολογισμός") force items wider than their track, causing horizontal overflow that clips or scrolls. Long single words additionally get `overflow-wrap:break-word` so they can wrap mid-word when they still don't fit.

**A note on rule order:** the file has both a base (desktop) `.tab-nav{ display:flex; }` rule and a later mobile-only `.tab-nav{ display:grid; }` override. Because CSS cascades per-*declaration*, not per-rule, a later unconditional rule can silently win over an earlier media-query rule for any property both declare — this bit us once (the mobile grid layout was being overridden back to flex) and needed a targeted `!important` to resolve. Worth remembering before assuming "it's in a media query so it must apply."

---

## 4. Core Calculation Logic

### 4.1 Net salary (`netFromGross`)
```
ss             = round(gross x ssRate%)
taxable        = gross - ss
annualTaxable  = taxable x 14                    (14-salary system)
grossAnnualTax = bracket_tax(annualTaxable, ageBracket)
usedCredit     = effectiveTaxCredit(baseCredit, annualTaxable)
annualTaxAfterCredit = max(grossAnnualTax - usedCredit, 0)
monthlyTax     = annualTaxAfterCredit / 14
net            = gross - ss - monthlyTax
```
Rounding (`r2`, round-to-cents) is applied after every intermediate step, matching how real payroll systems round, not just at the final result. This was verified line-for-line against a real payslip.

### 4.2 Age-based tax brackets
Three bracket tables (`TAX_BRACKETS_BY_AGE`), selected by the `ageBracket` field:
```
standard (>30):    9% | 20% | 26% | 34% | 39% | 44%
                   thresholds: EUR10k / EUR20k / EUR30k / EUR40k / EUR60k

young30 (26-30):   9% flat to EUR20k, then same upper brackets as standard
                   (26% | 34% | 39% | 44%)

young25 (<=25):    0% to EUR20k, then same upper brackets as standard
                   (26% | 34% | 39% | 44%)
```
Age only changes the tax scale — it does not affect EFKA contributions or the tax credit.

### 4.3 Tax credit taper (`effectiveTaxCredit`)
```
if annualTaxable <= 12000:
    usedCredit = baseCredit
else:
    reduction  = 20 x (annualTaxable - 12000) / 1000
    usedCredit = max(baseCredit - reduction, 0)
```
Full credit (default EUR777, adjustable for dependents) applies for annual taxable income <= EUR12,000; above that it decreases EUR20 per additional EUR1,000, floored at 0.

### 4.4 Bonuses (Christmas, Easter, leave allowance)
```
employedDays = days between max(hireDate, periodStart) and periodEnd
totalDays    = days between periodStart and periodEnd
ratio        = employedDays / totalDays              (0 if hireDate > periodEnd)
bonusGross   = fullAmount x ratio
bonusNet     = bonusGross x (regularNet / regularGross)
```
Periods: Christmas + leave allowance -> **May 1 - Dec 31** of the current year. Easter -> **Jan 1 - Apr 30** of the current year.

Each bonus's **net** amount is derived by applying the regular salary's effective net ratio (`net / gross`), not a separate tax calculation — bonuses are taxed at the same average rate as the regular salary rather than being independently annualized.

### 4.5 Extra hours (overwork / overtime / holiday work)
```
hourlyWage    = gross / 25 / 6.667
overworkGross = hours x hourlyWage x 1.20
overtimeGross = hours x hourlyWage x 1.40
holidayGross  = hours x hourlyWage x 0.75   (supplement only -- base day pay
                                              is already covered by the monthly salary)
```
**Correction, confirmed by multiple official sources:** extra-hours premiums are **exempt from EFKA contributions** for full-time employees, per Article 41 of Law 5184/2025 (as amended by Article 73 of Law 5239/2025) and e-EFKA circulars 8/2025 and 21/2025. This was initially implemented incorrectly (EFKA charged on the combined total) after over-indexing on a single real payslip that turned out to not correctly apply this exemption; the law itself, and every independent payroll/tax source describing it, was cross-checked afterward and confirms the exemption. Income tax is **not** exempted -- it still applies to the combined total through the same progressive scale, only the EFKA base is narrower:
```
ss            = round(gross x ssRate%)              (EFKA on REGULAR gross only)
combinedGross = gross + extraGross                    (tax base includes extra hours)
taxable       = combinedGross - ss
... same progressive-tax pipeline as Section 4.1, using this taxable ...
combinedNet   = combinedGross - ss - monthlyTax
extraPayNet   = combinedNet - regularNet              (marginal contribution)
netTotal      = combinedNet
```
The extra pay's displayed "net" figure is the *marginal difference* between the combined-total net and the regular-only net — i.e. what the extra hours actually add to take-home pay once progressive taxation is accounted for, not an isolated flat-rate calculation. A real payslip is useful for sanity-checking a formula, but is not a substitute for the primary source when the two disagree -- a single company's payroll system can misapply a law change; a law, ministry page, and several independent circulars agreeing with each other are much stronger evidence.

Known gap: a fourth premium tier exists in law (N.4808/2021) for legal overtime beyond 150 hours/year (+60%) and illegal overtime (+120%). The tool currently only models +20% (overwork) / +40% (overtime) / +75%-supplement (holiday work).

### 4.6 Cross-tab state (module-level globals)
`recomputeSalary()` writes: `lastNetSalary`, `lastExtraNet`, `lastAvgBonusEquiv`, `lastXmasNet`, `lastEasterNet`, `lastLeaveNet`.
`recompute()` (loan) writes: `lastMonthlyPayment`.
`recomputeBudget()` writes: `lastSavingsSuggestion`, `lastAllocationSurplus`, `lastPureVehicleCost`.
These are read across tabs — e.g. the Budget tab's remaining-balance calculation reads `lastNetSalary` regardless of which tab is currently visible, which is what lets the tool present a coherent picture instead of several isolated calculators. `updateHubCards()` reads from the *already-rendered* summary bar, DTI badge, and vehicle-cost DOM values rather than recomputing anything itself — the Hub is a pure mirror, never a second source of truth.

### 4.7 Loan amortization
```
r = annualRate / 12
M = P x r / (1 - (1 + r)^-n)
```
Standard French amortization (fixed monthly payment `M`, principal `P`, `n` installments). Schedule built month-by-month (`buildSchedule`) tracking interest/principal/balance per row.

### 4.8 Partial prepayment
```
newBalance = balanceAtMonth - prepaymentAmount

mode = "shorten":  keep M fixed,  solve for new n  (fewer remaining installments)
mode = "lower":    keep n fixed,  solve for new M  (smaller installment)
```
Both modes rebuild a full schedule from the reduced balance to compute interest saved.

### 4.9 Debt-to-income (DTI) indicator
```
pct = (lastMonthlyPayment / lastNetSalary) x 100

pct < 30        -> "ok"   (sufficient)
30 <= pct <= 35 -> "warn" (marginal)
pct > 35        -> "over" (insufficient / above typical bank threshold)
```
Compared against the 30-35% range Greek banks commonly use as a lending guideline. Framed explicitly as a bank rule of thumb, not a guarantee or the tool's own recommendation. The same three-tier language (Section 6... see terminology note in Section 5) is reused for the overall budget status, so the two indicators read consistently.

### 4.10 Investment calculator
Month-by-month simulation (not a closed-form formula), so mismatched contribution/compounding frequencies resolve correctly:
```
effectiveAnnualRate = (1 + rate/compoundFreq)^compoundFreq - 1
monthlyRate          = (1 + effectiveAnnualRate)^(1/12) - 1

for each month:
    balance = balance x (1 + monthlyRate)
    if contribution is due this month:
        balance = balance + contributionAmount
```
Lives in its own tab (`#tabInvest`); the contribution field auto-fills from the Budget tab's suggested savings amount unless manually overridden (tracked via a `touched` flag on the field, with a small "re-sync" affordance to clear it).

### 4.11 Budget & bonus allocation
```
for each of the 6 permutations of {insurance, roadTax, service}
    assigned to {Christmas, Easter, leaveAllowance}:
        covered   = count of pairs where bonus >= expense
        shortfall = sum of |bonus - expense| across all pairs
pick the permutation maximizing `covered`, then minimizing `shortfall`
surplus = sum(bonus - matchedExpense) across the winning permutation
```
Any surplus feeds the suggested reserve-fund addition. This runs independent of whether a loan exists, since vehicle expenses are meaningful whether or not the vehicle was financed.

### 4.12 Vehicle cost vs. loan payment (avoiding double-counting)
The Budget tab's own "Total Monthly Vehicle Cost" box (`fMotoTotal`) intentionally *includes* the loan payment (`motoTotal = lastMonthlyPayment + fixedMonthlyEquiv + variableMonthly`), because it sits directly beneath a separate "Loan Payment" line in the same card — the pairing makes the inclusion self-evident there.

Reusing that same combined figure elsewhere (the Hub card, the print report) turned out to double-count the loan: both a standalone "Loan" section/card *and* a "Vehicle Expenses" section/card would each show a number that included the same payment, with no adjacent line to clarify it. Fixed by tracking a second global, `lastPureVehicleCost = fixedMonthlyEquiv + variableMonthly` (no loan), and using *that* for any context where the vehicle total is shown without its loan figure directly alongside it. The lesson: a combined total is only safe to reuse in the exact layout context that justified combining it in the first place — anywhere else, use the disaggregated figure.

### 4.13 Employment type branching (salaried 14 / salaried 12)
A single `employmentType` dropdown (`salaried14` / `salaried12`) drives which fields and results are shown in the Salary tab, via container toggles in `recomputeSalary()`:
```
salariedOnlyFields -> gross salary, hire date, insurance category, EFKA %
extraHoursFields    -> overwork/overtime/holiday hours, extra net
```
`taxCredit` and `ageBracket` are shared, kept outside any mode-specific wrapper.

**A note for future reference:** a blokaki (ΔΠΥ-taxed-as-employee) mode was fully built, tested, and cross-checked against multiple sources and third-party calculators in an earlier revision, then deliberately removed at the user's request pending a rethink of its design -- not because the numbers were found to be wrong. If revisited, the earlier implementation covered: fixed and percentage-based EFKA options, a gross<->net calculation-direction toggle (net->gross solved via bisection, since the bracket+credit function has no closed-form inverse), a 2025-vs-2026 tax-scale comparison, and an informational (non-deducting) VAT line linked to an AADE reference page. A wrapper-scoping bug was also caught and fixed during that work: a "shared" field must be verified to sit *outside* every mode-specific container, not just declared shared in a comment.

### 4.15 Reusable info-icon / popover pattern
A small `.info-icon` (a "little i" glyph) paired with a `.info-popover` (hidden by default, toggled via an `open` class) is used for supplementary explanations that don't fit inline in a label -- first introduced for the insurance-category dropdown, written generically enough to reuse anywhere else a short explanatory aside is needed.

Toggling is handled by two **delegated** listeners on `document` (click and keydown), rather than listeners attached directly to each icon element:
```
document.addEventListener('click', e => { ...toggle the popover matching e.target.closest('.info-icon')... });
document.addEventListener('keydown', e => { ...same, for Enter/Space... });
```
Delegation matters here for the same reason noted in Section 5's "known trap": if a listener were attached directly to an icon element found at load time, it would be silently lost the moment that element's *ancestor* gets its `innerHTML` replaced by a language switch (a fresh DOM node replaces the old one, listeners and all). Delegating from `document` means the check happens at click-time against whatever is currently in the DOM, so it survives translation swaps for free.

**A real bug this produced:** the icon was initially placed *inside* the `<label for="...">` it annotated. Clicking anywhere inside a `<label>` also fires a synthetic click on the labeled form control (this is standard browser behavior, not a bug in our code) -- which bubbles to the same document-level listener a moment later, gets treated as "clicked outside the popover," and immediately closes the popover that had just been opened by the first click. Fixed by moving the icon to be a *sibling* of the label rather than a child of it.

---

## 5. Internationalization (i18n)

Every static string carries a `data-i18n="key"` attribute. Two dictionaries (`TRANSLATIONS.el`, `TRANSLATIONS.en`) hold the full innerHTML for each key (including nested `<span>` sub-notes, so translation can't accidentally strip inline styling). `applyStaticTranslations()` walks all `[data-i18n]` elements on load and on language toggle, replacing `innerHTML` from the active dictionary. Placeholder text uses a parallel `data-i18n-ph` attribute; `aria-label` uses `data-i18n-aria` (added when the Hub's icon-only home button needed a translated label with no visible text to carry it).

Dynamic (JS-generated) strings — tips, banners, badge/pill text, the print report, the Hub cards' detail lines — are **not** in the dictionary; each call site branches on `currentLang` directly with inline ternaries.

**Status terminology:** the budget/DTI status pill uses **Eparkes / Oriako / Aneparkes** (Sufficient / Marginal / Insufficient) rather than more colloquial or more jargon-heavy alternatives — chosen after two rounds of feedback: plain-language options ("sou perissevei") read as too casual for an experienced user, while the original finance jargon ("Pleonasma/Elleimma") wasn't self-explanatory to a first-time visitor. The chosen terms describe the *state of the balance* directly, in neutral register, understandable without financial vocabulary.

**Known trap:** static elements' *initial* HTML content is cosmetic only — the dictionary entry is what actually renders, since `applyStaticTranslations()` overwrites it immediately on load. Any change to a label (e.g. renumbering a section, shortening a tab name) must be made in **both** the HTML and the corresponding dictionary entries in both languages, or the dictionary's stale value silently reappears. This caused a real regression during development (renumbered sections showing old numbers) and is worth remembering for any future content changes.

Currency formatting (`euro`/`euroDec`) switches locale (`el-GR` vs `en-IE`) based on `currentLang`, so the same numeric value renders as `1.234,56 EUR` or `EUR1,234.56` correctly. Any value written into an `<input>` field programmatically uses `.toFixed(2)` rather than a bare rounded number — assigning a raw JS float (even one already passed through `r2()`) to `.value` can still surface binary floating-point artifacts like `232.95600000000002` in the rendered field; `.toFixed(2)` guarantees a clean two-decimal string.

---

## 6. Input Validation

HTML `min`/`max` attributes only affect the spinner arrows — they do **not** block manually typed out-of-range values. Real enforcement happens in a `FIELD_BOUNDS` map plus a `blur` listener per field that clamps the typed value (not on every keystroke, so users can type freely mid-edit):
```
if min is set and value < min: value = min
if max is set and value > max: value = max
```
Applied bounds: percentages capped 0-100 (interest rate, EFKA rate, savings %, investment return), non-negative amounts everywhere, sane upper caps on hour fields (300) and terms (installments <=600, investment years <=100).

---

## 7. Known Limitations

- Extra-hours premium tiers beyond +40% (the 150-hour/year threshold and illegal-overtime rates) are not modeled (Section 4.5).
- The bonus-to-vehicle-expense allocation assumes exactly three fixed expense categories; it isn't generalized for arbitrary category counts.
- No persistence — there is intentionally no save/load mechanism (removed by design once the print report existed as an alternative); each session starts from defaults.
- Loan prepayment assumes no fees/insurance/early-repayment penalties.
- A ~1-cent discrepancy occasionally appears in some display splits, sourced from floating-point rounding order differences versus an independent reference implementation; it does not affect final totals and has been reproduced and judged negligible.
- The insurance-category dropdown (Section 4.13's `salariedOnlyFields`) offers a small fixed set of categories (standard, heavy/unhealthy, underground/underwater); it isn't an exhaustive list of every EFKA sub-category, and the "adjust manually" option exists precisely because of that.

---

## 8. Deployment & SEO

Hosted on GitHub Pages (`main` branch, root). SEO surface: descriptive `<title>` and a `<meta description>` deliberately kept under ~155 characters (Google truncates SERP snippets around there — an earlier, longer description was being cut mid-word), Open Graph + Twitter Card tags with a generated 1200x630 preview image, `sitemap.xml`, `robots.txt`, Google Search Console verification (both meta-tag and HTML-file methods present for redundancy). `lang="el"` on `<html>` ensures correct Greek uppercase mapping (tonos-stripping) wherever `text-transform:uppercase` is used — this only works correctly when the language attribute is set, which is worth remembering if the markup is ever repurposed (e.g. the OG-image generation template initially lacked it and rendered incorrectly as a result).

The visible on-page intro text and the `<meta description>` are deliberately different: the former is short and brand-toned (what a human reader sees first), the latter stays keyword-dense within its display budget (what a search engine surfaces). Changing one doesn't require changing the other.

Repository includes an MIT `LICENSE` and a small footer signature/attribution line, added once the project moved from a private tool to something publicly hosted.

**Browser caching:** `style.css` and `script.js` are referenced with a version query string (`style.css?v=YYYYMMDD`) rather than a bare filename. Without this, a returning visitor's browser can keep serving an old cached copy of these files indefinitely after an update — clearing cookies does **not** clear the browser's file cache, so "I cleared my cookies and it's still broken" is a real, confusing symptom of this exact issue (confirmed: incognito mode, which starts with an empty cache, showed the update correctly while the same browser's normal window did not). Bump the version string whenever `style.css` or `script.js` changes in a way that matters to already-cached visitors.

**This bit us for real, not just hypothetically:** the version string was introduced once and then not bumped across several days of further edits (the entire blokaki build-and-removal, the Hub card fixes). A returning visitor ended up on a stale, partially-broken intermediate `script.js` — served entirely from their own cache under the unchanged `?v=` value — showing blank dashes everywhere, while a fresh test of the actual current file worked perfectly. The lesson: adding a cache-busting mechanism once is not the fix; *actually bumping it on every subsequent substantive edit* is the fix, and it's easy to forget precisely because the local/test environment never has a stale cache to reveal the problem.

---

## 9. Quality Assurance

`tests/qa_tests.py` is a Playwright-driven regression suite that opens `index.html` in a real headless browser and checks:
- Loan amortization and partial-prepayment figures against independently-verified reference values
- Salary/tax output, including the combined-gross extra-hours treatment (Section 4.5)
- Investment calculator growth
- Vehicle-cost vs. loan double-counting (Section 4.12)
- Hub dashboard default view and card-to-tab navigation
- Horizontal-overflow-free rendering at 320/375/412px, in both languages, across every tab
- Input clamping (Section 6)
- 12-salary annualization, and that switching employment types correctly shows/hides the bonus table and hire-date field (Section 4.13)
- Insurance-category dropdown auto-fills the EFKA rate, and that "adjust manually" leaves a hand-typed rate untouched

Run it with:
```
pip install playwright
playwright install chromium
python tests/qa_tests.py
```
Exits non-zero if any check fails, printing which one(s). Every reference value in the suite was itself cross-checked against an independent Python re-implementation of the relevant formula (or, for the salary/tax logic, a real payslip) before being hard-coded as the expected result — the point of the suite is to catch *regressions* against known-good numbers, not to (re-)establish that the numbers are correct in the first place.

`tests/lint_checks.py` is a separate, purely static script (no browser needed) that catches two specific bug *patterns* this project shipped more than once, rather than checking behavior:
1. **Nested `data-i18n` attributes** — an element with its own `data-i18n` sitting inside another `data-i18n` element gets silently destroyed the moment the outer element's `innerHTML` is reassigned by `applyStaticTranslations()`. Parses `index.html` with Python's `html.parser` (a real parser, not regex) to track element nesting and flag any such case.
2. **Cache-version drift** — compares the current MD5 hash of `style.css`/`script.js` against the hash recorded the last time the script ran successfully (stored in `tests/.cache_version_state.json`, isolated per checked directory via `--dir`); fails if the content changed but the `?v=` query string in `index.html` didn't, which is exactly the mistake that once shipped a broken page to returning visitors (§8).

Run it with:
```
python tests/lint_checks.py
```
Run both this and `qa_tests.py` before every deploy — they catch different classes of bug. A nested-`data-i18n` bug in particular is easy for behavioral testing to miss entirely, since the *initial* render in the default language is often unaffected; it only surfaces on a language switch, and only for that one nested element.

---

## 10. Sources & Verification

Every rule this tool implements was checked against a primary source before being coded, and re-checked whenever a change was made to it. This section collects those sources in one place, organized by what they support, rather than leaving them scattered across §4's commit-by-commit notes.

**Primary/official sources (government):**
- **Ministry of Labour** (ypergasias.gov.gr) — employee/employer EFKA contribution rates and their breakdown (main pension, auxiliary, heavy/unhealthy occupation surcharge, underground/underwater work surcharge), the monthly contribution ceiling. Fetched directly: `ypergasias.gov.gr/koinoniki-asfalisi/asfalismenoi-eisfores-kai-paroches/asfalistikes-eisfores/`.
- **AADE** (Independent Authority for Public Revenue, aade.gr) — VAT declaration information, linked directly from the VAT field's info icon. Fetched and confirmed live: `aade.gr/diloseis-fpa-vies`.
- **Ν.5184/2025 Άρθρο 41**, as amended by **Ν.5239/2025 Άρθρο 73** — the EFKA exemption for overwork/overtime/holiday-work premiums (§4.5); confirmed consistent across the Ministry of Labour page and multiple independent payroll/tax sources, not just one.
- **e-ΕΦΚΑ circulars 8/2025 and 21/2025** — implementation guidance for the same exemption.

**Cross-referenced secondary sources (tax-advisory sites, news outlets):** used to triangulate figures where no single government page gave the full picture, or to sanity-check a government-sourced figure from an independent angle — never used as the sole basis for a number. Where a secondary source *disagreed* with another, the discrepancy was investigated and resolved (or the disagreement itself documented) rather than picking one arbitrarily — see the 2025-vs-2026 tax-bracket reconciliation and the third-party blokaki-calculator cross-check, both in §4's revision history, as worked examples of that process.

**What this means practically:** no figure in this tool is "we assumed" — each has a traceable origin, and several (EFKA contribution amounts, the overtime EFKA exemption, the advance-tax-payment rate) are corroborated by more than one independent source. Where confidence is *lower* than this standard — the young-age 2025 tax brackets being the clearest example — that's stated explicitly in the relevant section rather than presented with the same confidence as a sourced figure.

---

## 11. Development Process

This section documents *how* changes get made to this project, not just what the result looks like — the workflow itself is treated as something worth getting right, following a mistake it was meant to prevent (§10.13's blokaki build-then-remove, and the repeated bug-pattern issues in §9's lint script).

**Spec-first for any non-trivial feature.** Before writing any code for a feature that isn't a small, obviously-scoped fix, the exact shape is written out in 3-4 plain sentences first — what field/input is added, what it outputs, and where in the UI it lives — and gets explicit confirmation before any implementation starts. "Non-trivial" means: touches more than one file, adds a new input the user has to understand, or changes an existing calculation's behavior. A one-line copy edit or an obvious bug fix doesn't need this; a new dropdown, a new calculation mode, or a new field does. This rule exists specifically because the blokaki feature was built in full (multiple rounds: initial version, renamed, gross-income model, 2025/2026 comparison, VAT) before being removed entirely at the user's request — not because anything was wrong with it, but because the exact shape hadn't been pinned down before implementation started. Confirming the shape first is far cheaper than building first and re-scoping after.

**dev/ → test → merge, never edit deploy/ directly.** All changes are made in `dev/` (a full working copy of the live files), verified there (`qa_tests.py`, `lint_checks.py`, manual scenario checks, mobile-width checks), diffed against `deploy/` line-by-line to confirm every removed line is an intentional, accounted-for replacement (not a silent loss), and only then copied over `deploy/`. `deploy/` is the only thing the user uploads to GitHub; `dev/` is disposable and gets overwritten freely between features.

**Both test scripts run before every merge, not just the behavioral one.** `qa_tests.py` (browser-driven, checks computed values and visibility) and `lint_checks.py` (static, checks for the two specific bug patterns in §9) each catch a different class of regression — a passing `qa_tests.py` run does not mean `lint_checks.py` would also pass, and vice versa.

**Bump the cache-busting version on every merge that touches `style.css` or `script.js`.** This is easy to forget precisely because nothing in the local test environment ever has a stale cache to reveal the omission (§8) — `lint_checks.py`'s cache-version check exists specifically to catch this without relying on remembering.

**When something looks broken after a merge, check the browser cache before assuming a code bug.** This happened twice in this project's history (§8) — both times the actual file was correct and the reported symptom was caused by a stale cached copy on the reporting device. A quick hard-refresh (`Ctrl+Shift+R` / `Cmd+Shift+R`) rules this out in seconds, before spending time debugging code that isn't broken.

---

## 12. First-Time-Visitor UX Review

A deliberate practice adopted mid-project: periodically browse the live tool with the same fresh-eyes lens a genuine first-time visitor would use — reading every tab's full text, not just checking whether numbers compute correctly — rather than relying solely on the person who already knows the tool intimately to notice friction. Three rounds of this review, spaced across several sessions, surfaced problems that behaved correctly (no bug, no wrong number) but were still confusing or unwelcoming on first contact. None of these were caught by `qa_tests.py`, which checks computed values and visibility, not whether the *experience* of encountering those values for the first time makes sense.

**Three distinct empty-state treatments, chosen deliberately per context rather than one rule applied everywhere:**
1. **Hide entirely** — used where an entire block of results is meaningless without a precondition (the Budget tab's loan-payment and vehicle-cost rows, hidden until a loan/vehicle is actually entered; the Loan tab's Partial Repayment comparison, hidden until a loan amount exists). Right when there's *nothing* to interpret, not even a placeholder.
2. **Dash + short note** — used where the section is the whole point of the tab and disappearing entirely would look broken (the Loan tab's main "Results" card shows "—" in every field plus "You haven't entered a loan amount yet." rather than vanishing).
3. **Real-time zero, no note** — used where the number updates live as the user types and a plain "€0.00" is the expected, informative state (the Vehicle Expenses tab's running total). The distinguishing factor across all three: whether zero is a *meaningful, complete* answer (treatment 3), a *technically correct but currently pointless* one (treatment 1), or *the whole reason this tab exists but not yet computable* (treatment 2).

**"Optional" field de-emphasis instead of hide/reveal.** The Salary tab's rarely-used fields (insurance category, overtime/overwork/holiday hours, business type) were considered for progressive disclosure (a "show more" toggle) but that was deliberately rejected: a returning user who already knows they need the overtime-hours field would have to re-click "show more" on every single visit, since the tool has no persistence between sessions (§7) — trading first-visit clarity for repeat-visit friction. The chosen alternative instead keeps every field always visible, grouped under a plain, quieter "Optional" heading (muted color, dashed top border) — zero extra clicks for anyone, and a lighter visual hierarchy on first contact.

**Scope-representation drift.** Two separate pieces of top-of-page copy (the small "eyebrow" label above the H1, and the intro paragraph below it) each independently undersold the tool's actual scope — one omitted Investments and Vehicle Expenses entirely, the other omitted Vehicle Expenses. Both were written when the tool covered fewer areas and were never revisited as features were added; nothing enforces that summary copy stays in sync with the feature set it's describing; only manual review catches this class of drift.

**A stale rename can hide in a branch that's rarely exercised.** The Reserve Fund's rename from "Vacation Fund" (`αποθεματικό διακοπών` → `αποθεματικό`, an earlier revision) missed two user-facing strings: the intro card's static description, and a sentence inside the bonus-allocation paragraph that only renders when fixed vehicle expenses are non-zero. A project-wide grep for the literal old string, run once after the rename, would have caught both immediately; relying on noticing them in ordinary use did not, since the second one specifically requires a non-default input state to even appear.

**A copy/paste-shaped wording bug can survive numeric correctness entirely.** A budget-tips message read "The vehicle absorbs about X% of your income" but was computed from `motoTotal`, which (by design, §4.12) includes the loan payment combined with vehicle costs — so the sentence was subtly misattributing a number that was arithmetically correct to the wrong cause. Caught by the user re-reading the tool's own output critically, not by any test, since the *number* was always right; only the *word* describing it was wrong. Fixed consistently across both severity branches of the same message (high-share warning and normal-range confirmation) and both languages, since all four variants share the same underlying value and an inconsistent fix would have left the same number labeled differently depending on which threshold it crossed.

**Badge terminology can be self-explanatory in its original context and opaque once copied elsewhere.** The Loan tab's DTI badge shows a bare percentage ("32%") — correct there, since the adjacent `dtiText` sentence spells out what the percentage means and how it compares to the 30–35% bank threshold. The Hub dashboard's Loan card copies only the badge, not the adjacent sentence, leaving a bare, uncontextualized number next to the Budget card's self-explanatory word ("Επαρκές"/"Sufficient"). Fixed by giving the Hub-specific copy its own short descriptive text (Within limit / At the edge / Above limit) derived from the same `ok`/`warn`/`over` classification, rather than reusing the tab's own badge text verbatim — the lesson being that copying a UI element's *text* to a new context doesn't carry over the *surrounding context* that made that text legible in the first place.

---

## 13. Business-Logic Validation Sweep

A deliberate pass looking specifically for a different class of problem than §12: not confusing-but-correct UX, but places where the *arithmetic itself* could be wrong or misleading for a valid combination of inputs. Several were found and fixed together.

**The "Reset to Defaults" button had quietly fallen behind the feature set.** Two parallel arrays (`EXPORT_FIELD_IDS`, which the reset loop iterates over, and `DEFAULT_VALUES`, which supplies the values) were each last updated before `employmentType`, `ssCategory`, `businessType`, and `holidayDays` existed. Clicking reset correctly restored every numeric input but silently left all four of those dropdowns/fields untouched — a half-reset that looked complete (no error, no visual cue) but wasn't. The lesson generalizes: *any* feature that maintains its own list of "all the fields that matter" (export, reset, a future save/load) needs a companion process for keeping that list current as fields are added elsewhere, since nothing structurally forces the connection.

**A field's displayed value can silently stop matching what's actually being computed.** The Partial Repayment section's "month of application" field had no `max`, while the calculation itself clamped it to the loan's installment count internally — so typing "30" against a 24-installment loan showed a result computed for month 24 while the field kept displaying 30, with no indication the two had diverged. Fixed by making the field's `max` track the loan's installment count dynamically and visibly correcting the displayed value the moment it's exceeded, rather than only correcting the number used internally. A secondary miss during the fix: the field had no `input`-event listener of its own, so typing directly into it didn't trigger the correction at all — only *other* fields changing (which happened to call the same recompute function) did. Every field a dynamic constraint applies to needs its own listener; a constraint enforced only as a side effect of unrelated fields' listeners is enforced incompletely.

**A result of exactly zero needs to be distinguishable from "you haven't told me anything yet."** When a down payment is entered that's greater than or equal to the loan amount, the financed principal correctly computes to zero — but the Loan tab's results previously displayed that identically to the "no loan amount entered" empty state (§12), even though the person had clearly entered real numbers. Fixed by giving this case its own message ("the down payment leaves nothing to finance") rather than reusing the generic empty-state text, so the *cause* of the zero is never ambiguous.

**A value bounded only by a field's own literal meaning can still be physically impossible.** "Holiday days worked" allowed up to 31 (calendar days in a month) with no reference to what a holiday actually is in Greece — Sundays plus a handful of fixed dates — so entering something like 20 was accepted despite no month having anywhere near that many. Capped to 8 (five Sundays plus the two fixed Christmas dates, with one day of margin) as a fixed ceiling rather than a real calendar-aware calculation (which would require implementing the Orthodox Easter algorithm for the moveable holidays and was judged disproportionate effort for a field this rarely used) — a deliberate scope call to take most of the value at a fraction of the cost, made explicit rather than silently skipped.

**A "shorten the term" prepayment result didn't check whether there was a term left to shorten.** When a prepayment fully paid off the remaining balance, the "installments remaining" figure correctly computed to zero, but the adjacent "monthly payment" figure was hard-coded to always redisplay the original payment amount regardless — producing "0 installments remaining" next to a non-zero monthly payment for those non-existent installments, an internal contradiction visible in a single screen. Caught by deliberately testing an overpayment scenario, not by any existing test. The parallel "reduce the payment" mode didn't share the bug, because its payment figure was already *computed* from the (possibly zero) remaining balance rather than assumed constant — the fix made the "shorten" branch follow the same principle: derive the displayed payment from whether anything is actually left, never assume it.

**Letting a field accept a small expression (`450+120+300`) instead of requiring pre-summed input** was added to the Budget tab's "other fixed expenses" field after noticing that summing rent+bills+other-loans externally before typing was a real, if minor, piece of friction — a genuine convenience, not scope creep, since it saves a trip to a separate calculator without adding any new concept to the tool. Implemented deliberately without `eval()`/`Function()` on user input, even though the character-whitelist filtering already in place would have made that reasonably safe in practice: a small hand-rolled tokenizer resolves `*`/`/` in a first pass before summing, so there is no code-execution surface at all rather than a filtered one. Division by zero or an incomplete expression (a trailing operator, an empty field) silently reverts to the last value that evaluated successfully, mirroring the existing numeric-field blur-clamp pattern elsewhere rather than introducing a new kind of error state. Converting the field from `type="number"` to `type="text"` (required, since number inputs block `+`/`*`/`/` at the browser level) meant removing it from the shared `FIELD_BOUNDS` blur-clamp system — that system's `parseFloat()`-based clamping would read only the leading number of an unresolved expression and silently truncate the rest, so the field now carries its own dedicated blur/Enter handler that performs both the expression resolution and the minimum-value clamp together, rather than risking two independent handlers racing on the same field.
