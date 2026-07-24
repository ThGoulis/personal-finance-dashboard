"""
Quality assurance test suite for the Personal Finance Dashboard.

Runs the application in a real (headless) browser via Playwright and checks:
  1. Core calculations against independently-verified reference values
     (loan amortization, salary/tax, prepayment scenarios, investment growth)
  2. Cross-tab / Hub dashboard behavior
  3. Mobile responsiveness (no horizontal overflow) across common widths,
     both languages, and every tab
  4. Basic regression checks after any future change

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    python tests/qa_tests.py
    python tests/qa_tests.py --file /path/to/index.html

Exits with status 0 if all checks pass, 1 if any check fails.
"""

import sys
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

FAILURES = []


def check(label, actual, expected, tolerance=0.01):
    """Compare a numeric-looking string/float against an expected value."""
    try:
        actual_num = float(str(actual).replace('.', '').replace(',', '.').replace('€', '').replace('%', '').strip())
    except ValueError:
        actual_num = None
    ok = actual_num is not None and abs(actual_num - expected) <= tolerance
    status = 'PASS' if ok else 'FAIL'
    print(f"  [{status}] {label}: got {actual!r}, expected ~{expected}")
    if not ok:
        FAILURES.append(label)


def check_bool(label, actual, expected):
    ok = actual == expected
    status = 'PASS' if ok else 'FAIL'
    print(f"  [{status}] {label}: got {actual!r}, expected {expected!r}")
    if not ok:
        FAILURES.append(label)


def run(file_url):
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ================= 1. Loan amortization =================
        print("\n=== 1. Loan amortization ===")
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        page.goto(file_url)
        page.wait_for_timeout(300)
        page.click('#tabBtnLoan')
        page.fill('#amount', '12000')
        page.dispatch_event('#amount', 'input')
        page.fill('#down', '2000')
        page.dispatch_event('#down', 'input')
        page.fill('#installments', '48')
        page.dispatch_event('#installments', 'input')
        page.fill('#rate', '9.5')
        page.dispatch_event('#rate', 'input')
        page.wait_for_timeout(150)
        check('Monthly payment', page.inner_text('#rMonthly'), 251.23)
        check('Total interest', page.inner_text('#rInterest'), 2059, tolerance=2)
        page.close()

        # ================= 2. Partial prepayment =================
        print("\n=== 2. Partial prepayment (shorten term) ===")
        page = browser.new_page()
        page.goto(file_url)
        page.wait_for_timeout(300)
        page.click('#tabBtnLoan')
        page.fill('#amount', '12000')
        page.dispatch_event('#amount', 'input')
        page.fill('#down', '2000')
        page.dispatch_event('#down', 'input')
        page.fill('#installments', '48')
        page.dispatch_event('#installments', 'input')
        page.fill('#rate', '9.5')
        page.dispatch_event('#rate', 'input')
        page.fill('#prepMonth', '12')
        page.dispatch_event('#prepMonth', 'input')
        page.fill('#prepAmount', '2000')
        page.dispatch_event('#prepAmount', 'input')
        page.click('#modeShorten')
        page.click('#computeBtn')
        page.wait_for_timeout(150)
        check('Interest saved (shorten)', page.inner_text('#beforeInterest'), 1265, tolerance=2)
        page.close()

        # ================= 3. Salary & tax (standard age bracket) =================
        print("\n=== 3. Salary & tax (standard, no extra hours) ===")
        page = browser.new_page()
        page.goto(file_url)
        page.wait_for_timeout(300)
        page.click('#tabBtnSalary')
        page.fill('#grossSalary', '1570')
        page.dispatch_event('#grossSalary', 'input')
        page.fill('#ssRate', '13.37')
        page.dispatch_event('#ssRate', 'input')
        page.select_option('#ageBracket', 'standard')
        page.wait_for_timeout(150)
        check('Social security (ss)', page.inner_text('#sSS'), -209.91)
        check('Net salary', page.inner_text('#sNet'), 1212.08)
        page.close()

        # ================= 4. Extra hours (combined-gross tax treatment) =================
        print("\n=== 4. Extra hours: combined EFKA + progressive tax ===")
        page = browser.new_page()
        page.goto(file_url)
        page.wait_for_timeout(300)
        page.click('#tabBtnSalary')
        page.fill('#grossSalary', '1200')
        page.dispatch_event('#grossSalary', 'input')
        page.fill('#ssRate', '13.37')
        page.dispatch_event('#ssRate', 'input')
        page.fill('#overworkHours', '7')
        page.dispatch_event('#overworkHours', 'input')
        page.fill('#overtimeHours', '1')
        page.dispatch_event('#overtimeHours', 'input')
        page.wait_for_timeout(150)
        check('Net total (regular + extra)', page.inner_text('#sNetTotal'), 1009.75, tolerance=0.05)
        page.close()

        # ================= 5. Investment calculator =================
        print("\n=== 5. Investment calculator ===")
        page = browser.new_page()
        page.goto(file_url)
        page.wait_for_timeout(300)
        page.click('#tabBtnInvest')
        page.evaluate("document.getElementById('invContribution').dataset.touched = 'true'")
        page.fill('#invStart', '1000')
        page.dispatch_event('#invStart', 'input')
        page.fill('#invYears', '5')
        page.dispatch_event('#invYears', 'input')
        page.fill('#invContribution', '100')
        page.dispatch_event('#invContribution', 'input')
        page.select_option('#invContribFreq', '12')
        page.fill('#invRate', '5')
        page.dispatch_event('#invRate', 'input')
        page.select_option('#invCompound', '12')
        page.wait_for_timeout(150)
        check('Total contributions', page.inner_text('#invTotalContrib'), 7000)
        check('Final balance', page.inner_text('#invFinalBalance'), 8083.97)
        page.close()

        # ================= 6. Vehicle cost vs loan (no double-counting) =================
        print("\n=== 6. Vehicle expenses vs loan payment (no double-counting) ===")
        page = browser.new_page()
        page.goto(file_url)
        page.wait_for_timeout(300)
        page.click('#tabBtnLoan')
        page.fill('#amount', '5000')
        page.dispatch_event('#amount', 'input')
        page.wait_for_timeout(150)
        page.click('#tabBtnMoto')
        page.fill('#motoInsurance', '600')
        page.dispatch_event('#motoInsurance', 'input')
        page.fill('#motoFuel', '80')
        page.dispatch_event('#motoFuel', 'input')
        page.wait_for_timeout(150)
        page.click('#tabBtnHub')
        page.wait_for_timeout(150)
        check('Hub vehicle cost (must exclude loan)', page.inner_text('#hubMotoValue'), 130.00)
        page.close()

        # ================= 7. Hub dashboard navigation =================
        print("\n=== 7. Hub dashboard navigation ===")
        page = browser.new_page()
        page.goto(file_url)
        page.wait_for_timeout(300)
        hub_display = page.evaluate("getComputedStyle(document.getElementById('tabHub')).display")
        check_bool('Hub is the default view', hub_display, 'block')
        page.click('#hubCardLoan')
        page.wait_for_timeout(150)
        loan_active = page.evaluate("document.getElementById('tabBtnLoan').classList.contains('active')")
        check_bool('Clicking a Hub card navigates to its tab', loan_active, True)
        page.close()

        # ================= 8. Mobile responsiveness =================
        print("\n=== 8. Mobile responsiveness (no horizontal overflow) ===")
        tab_ids = ['tabBtnHub', 'tabBtnSalary', 'tabBtnBudget', 'tabBtnInvest', 'tabBtnMoto', 'tabBtnLoan']
        for width in [320, 375, 412]:
            page = browser.new_page(viewport={'width': width, 'height': 900})
            page.goto(file_url)
            page.wait_for_timeout(250)
            page.click('#tabBtnLoan')
            page.fill('#amount', '30000')
            page.dispatch_event('#amount', 'input')
            page.fill('#installments', '12')
            page.dispatch_event('#installments', 'input')
            page.wait_for_timeout(150)
            for lang in ['EL', 'EN']:
                for tab in tab_ids:
                    page.click(f'#{tab}')
                    page.wait_for_timeout(80)
                    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                    check_bool(f'No overflow @ {width}px [{lang}] {tab}', overflow, False)
                page.click('#langToggleBtn')
                page.wait_for_timeout(80)
            page.close()

        # ================= 9. Input validation / clamping =================
        print("\n=== 9. Input validation (clamping on blur) ===")
        page = browser.new_page()
        page.goto(file_url)
        page.wait_for_timeout(300)
        page.click('#tabBtnSalary')
        page.fill('#ssRate', '150')
        page.evaluate("document.getElementById('ssRate').dispatchEvent(new Event('blur'))")
        page.wait_for_timeout(100)
        check_bool('ssRate clamps to 100 max', page.input_value('#ssRate'), '100')
        page.fill('#grossSalary', '-500')
        page.evaluate("document.getElementById('grossSalary').dispatchEvent(new Event('blur'))")
        page.wait_for_timeout(100)
        check_bool('grossSalary clamps to 0 min', page.input_value('#grossSalary'), '0')
        page.close()

        print("\nJavaScript errors encountered:", errors)
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', default=None, help='Path to index.html (defaults to ../index.html relative to this script)')
    args = parser.parse_args()

    if args.file:
        target = Path(args.file).resolve()
    else:
        target = (Path(__file__).parent / '..' / 'index.html').resolve()

    if not target.exists():
        print(f"Could not find {target}")
        sys.exit(1)

    run(f'file://{target}')

    print(f"\n{'='*50}")
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("RESULT: all checks passed.")
        sys.exit(0)
