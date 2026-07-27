"""
Structural lint checks for the Personal Finance Dashboard.

Distinct from tests/qa_tests.py (which drives a real browser and checks
*behavior* -- computed numbers, visibility, navigation). This script parses
the files *statically* and checks for two specific patterns that have each
caused a real, shipped bug more than once during this project's development:

1. Nested data-i18n attributes. applyStaticTranslations() overwrites a
   data-i18n element's innerHTML wholesale on load and on every language
   switch. Any element with its own data-i18n sitting *inside* another one
   gets silently destroyed the moment the outer element's HTML is
   reassigned -- its node is gone, not just re-styled. This exact mistake
   shipped at least three times in this project (an info icon nested in a
   label, a link nested in a label, a span nested in a section heading).

2. Cache-busting version drift. style.css and script.js are referenced with
   a `?v=YYYYMMDD` query string specifically so returning visitors' browsers
   fetch a fresh copy after an update (see TECHNICAL.md's "Browser caching"
   note). The mechanism only works if the version string is actually bumped
   every time the file content changes -- and it was forgotten for several
   days of real edits, shipping a visibly broken page to a returning
   visitor. This check compares the current content hash of style.css/
   script.js against the hash recorded the last time this script ran
   successfully; if the content changed but the version string in index.html
   didn't, it fails loudly instead of silently.

Usage:
    python tests/lint_checks.py
    python tests/lint_checks.py --dir /path/to/deploy

Exits 0 if clean, 1 if either check finds a problem. Run this alongside
qa_tests.py before every deploy -- it catches a different class of bug that
qa_tests.py's behavioral checks can't (a nested data-i18n bug is often
invisible in an automated test because the *default* language still renders
correctly; it only breaks on a language switch or a second render pass, and
even then only for that one nested element).
"""

import sys
import json
import hashlib
import argparse
from pathlib import Path
from html.parser import HTMLParser

FAILURES = []


class NestedI18nChecker(HTMLParser):
    """Walks the HTML tag tree, tracking which data-i18n element (if any) is
    currently open, and flags any data-i18n tag found while another is
    already open -- that's the exact nesting pattern that gets destroyed."""

    # Tags that don't need a closing tag; treating these as "void" avoids
    # mis-tracking the stack depth (e.g. <input>, <br>, <img>).
    VOID_TAGS = {'input', 'br', 'img', 'hr', 'meta', 'link', 'source', 'area', 'col'}

    def __init__(self):
        super().__init__()
        self.stack = []          # stack of (tag_name, has_i18n)
        self.open_i18n_key = None  # data-i18n value of the currently-open ancestor, if any
        self.violations = []      # list of (inner_key, outer_key)

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        has_i18n = 'data-i18n' in attrs_dict
        if has_i18n and self.open_i18n_key is not None:
            self.violations.append((attrs_dict['data-i18n'], self.open_i18n_key))
        if tag not in self.VOID_TAGS:
            self.stack.append((tag, attrs_dict.get('data-i18n') if has_i18n else None))
            if has_i18n and self.open_i18n_key is None:
                self.open_i18n_key = attrs_dict['data-i18n']

    def handle_endtag(self, tag):
        # Pop back to (and including) the matching start tag, being tolerant
        # of any mismatched/unclosed tags rather than crashing the check.
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                popped = self.stack[i:]
                del self.stack[i:]
                # If we just closed the element that owns open_i18n_key, clear it.
                if any(key == self.open_i18n_key for _, key in popped) and self.open_i18n_key is not None:
                    # Recompute from what remains open, in case of multiple levels.
                    self.open_i18n_key = next((key for _, key in reversed(self.stack) if key), None)
                break


def check_nested_data_i18n(html_path):
    print(f"\n=== Nested data-i18n check ({html_path.name}) ===")
    content = html_path.read_text(encoding='utf-8')
    checker = NestedI18nChecker()
    checker.feed(content)
    if checker.violations:
        for inner, outer in checker.violations:
            msg = f'data-i18n="{inner}" is nested inside data-i18n="{outer}" -- the inner element will be destroyed on language switch'
            print(f"  [FAIL] {msg}")
            FAILURES.append(msg)
    else:
        print("  [PASS] No nested data-i18n elements found")


def check_cache_version(deploy_dir):
    print(f"\n=== Cache-busting version check ===")
    index_path = deploy_dir / 'index.html'
    style_path = deploy_dir / 'style.css'
    script_path = deploy_dir / 'script.js'
    state_path = deploy_dir / 'tests' / '.cache_version_state.json'

    index_content = index_path.read_text(encoding='utf-8')
    style_hash = hashlib.md5(style_path.read_bytes()).hexdigest()
    script_hash = hashlib.md5(script_path.read_bytes()).hexdigest()

    import re
    style_version_match = re.search(r'style\.css\?v=(\S+?)"', index_content)
    script_version_match = re.search(r'script\.js\?v=(\S+?)"', index_content)
    current_style_version = style_version_match.group(1) if style_version_match else None
    current_script_version = script_version_match.group(1) if script_version_match else None

    if current_style_version is None or current_script_version is None:
        msg = "Could not find ?v= cache-busting query string on style.css or script.js in index.html"
        print(f"  [FAIL] {msg}")
        FAILURES.append(msg)
        return

    if state_path.exists():
        prev = json.loads(state_path.read_text(encoding='utf-8'))
    else:
        prev = None

    if prev is None:
        print("  [INFO] No prior recorded state -- recording current state as the baseline.")
    else:
        style_changed = prev.get('style_hash') != style_hash
        script_changed = prev.get('script_hash') != script_hash
        version_unchanged = (prev.get('style_version') == current_style_version
                             and prev.get('script_version') == current_script_version)
        if (style_changed or script_changed) and version_unchanged:
            msg = (f"style.css and/or script.js content changed since the last recorded check, "
                   f"but the ?v= version string ({current_style_version}) was not bumped. "
                   f"Returning visitors' browsers may keep serving the stale cached copy.")
            print(f"  [FAIL] {msg}")
            FAILURES.append(msg)
        elif style_changed or script_changed:
            print(f"  [PASS] Content changed and version string was bumped accordingly "
                  f"({prev.get('style_version')} -> {current_style_version})")
        else:
            print("  [PASS] No content change since last recorded check")

    state_path.write_text(json.dumps({
        'style_hash': style_hash,
        'script_hash': script_hash,
        'style_version': current_style_version,
        'script_version': current_script_version,
    }, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', default=None, help='Path to the deploy directory (defaults to the parent of this script\'s folder)')
    args = parser.parse_args()

    deploy_dir = Path(args.dir).resolve() if args.dir else (Path(__file__).parent / '..').resolve()

    check_nested_data_i18n(deploy_dir / 'index.html')
    check_cache_version(deploy_dir)

    print(f"\n{'='*50}")
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("RESULT: all structural checks passed.")
        sys.exit(0)
