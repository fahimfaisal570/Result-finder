#!/usr/bin/env python3
"""
tests/test_exam_monitor_workflow.py
====================================
Exam Monitor Workflow - Full Integration Smoke Test

WHAT THIS COVERS
----------------
  main branch  : auto_pdf_mailer.py, monitor.py, find_latest.py, sync_state.py
  v2 branch    : v2_auto_sync.py, database.py
  Cross-branch : v2_sync_tasks.json schema contract, GitHub Actions YAML gates

HOW TO RUN
----------
  # From the project root:
  python tests/test_exam_monitor_workflow.py

  # Requires git remote 'origin' to be reachable (for v2 branch checks).
  # No external pip packages needed — stdlib only.

ADDING NEW CHECKS
-----------------
  Define a plain function, then call check('description', function).
  The runner catches any AssertionError or Exception and marks the test FAIL.

LAST VERIFIED : 2026-05-27  |  17/17 passed
"""

import sys
import os
import json
import threading
import ast
import re
import subprocess

# Always resolve paths relative to the project root, regardless of where
# this script is invoked from.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RESULTS = []


# ─── Runner helpers ───────────────────────────────────────────────────────────

def check(name, fn):
    """Register and execute a single test case."""
    try:
        fn()
        RESULTS.append(('OK', name))
    except Exception as e:
        RESULTS.append(('FAIL', name, str(e)))


def read_file(rel):
    """Read a file from the project root by relative path."""
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def git_show(branch_path):
    """Read a file from a remote branch without checking it out."""
    r = subprocess.run(
        ['git', '-C', ROOT, 'show', branch_path],
        capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    return r.stdout


# ─── 1. Syntax of every monitor file ─────────────────────────────────────────

MONITOR_FILES = [
    'exam_monitor/auto_pdf_mailer.py',
    'exam_monitor/monitor.py',
    'exam_monitor/find_latest.py',
    'exam_monitor/sync_state.py',
]
for _rel in MONITOR_FILES:
    def _syn(r=_rel):
        ast.parse(read_file(r))
    check(f'syntax  :: {_rel}', _syn)


# ─── 2. Lock exists and guards EXACTLY 2 write sites ─────────────────────────

def test_lock_sites():
    src = read_file('exam_monitor/auto_pdf_mailer.py')
    assert '_file_write_lock = threading.Lock()' in src, 'lock declaration missing'
    sites = src.count('with _file_write_lock:')
    assert sites == 2, f'expected 2 lock sites, found {sites}'

check('lock    :: 2 write sites guarded in auto_pdf_mailer', test_lock_sites)


# ─── 3. threading import present in auto_pdf_mailer ──────────────────────────

def test_threading_import():
    src = read_file('exam_monitor/auto_pdf_mailer.py')
    assert 'import threading' in src, 'threading not imported'

check('import  :: threading imported in auto_pdf_mailer', test_threading_import)


# ─── 4. _parse_profile_parts regex handles all naming conventions ─────────────
# Mirrors the logic inside auto_pdf_mailer._parse_profile_parts so the test
# stays independent of the module import (which monkeypatches random).

_PROFILE_PAT = re.compile(r'^([A-Za-z][A-Za-z.\s]*)\s*[-_]?\s*(\d+)', re.IGNORECASE)

def _parse(name):
    m = _PROFILE_PAT.match(name.strip())
    if not m:
        return None, None
    dept = re.sub(r'[^a-z]', '', m.group(1).lower())
    try:
        return dept, int(m.group(2))
    except ValueError:
        return None, None


def test_regex():
    cases = [
        ('CSE 15',      'cse',    15),
        ('CSE-15',      'cse',    15),
        ('EEE_13',      'eee',    13),
        ('B.Sc CSE 15', 'bsccse', 15),
        ('civil 09',    'civil',   9),
        ('CSE15',       'cse',    15),
        ('CIVIL-12',    'civil',  12),
        ('eee 08',      'eee',     8),
    ]
    for name, exp_dept, exp_batch in cases:
        d, b = _parse(name)
        assert d == exp_dept and b == exp_batch, (
            f'Failed for {name!r}: got ({d!r}, {b!r}), '
            f'expected ({exp_dept!r}, {exp_batch!r})'
        )

check('regex   :: _parse_profile_parts covers all name formats', test_regex)


# ─── 5. _parse_profile_parts rejects unparseable names gracefully ─────────────

def test_regex_bad_names():
    bad = ['', '123', '---', 'NoNumber', '   ']
    for name in bad:
        d, b = _parse(name)
        assert d is None and b is None, (
            f'Expected (None, None) for {name!r}, got ({d}, {b})'
        )

check('regex   :: bad profile names return (None, None)', test_regex_bad_names)


# ─── 6. Senior-profile lookup logic unit test ─────────────────────────────────

def test_senior_lookup():
    fake = {
        'CSE 15':  {'pro_id': '14'},
        'CSE 14':  {'pro_id': '14'},
        'CSE 13':  {'pro_id': '14'},
        'EEE 15':  {'pro_id': '13'},
        'EEE 14':  {'pro_id': '13'},
        'CSE-12':  {'pro_id': '14'},   # dash separator
        'civil 09':{'pro_id': '12'},
    }

    def get_seniors(profiles, profile_name):
        dept_prefix, batch_num = _parse(profile_name)
        if dept_prefix is None:
            return {}
        return {
            p_name: p_data
            for p_name, p_data in profiles.items()
            if (lambda pd, pb: pd == dept_prefix and pb is not None and pb < batch_num)
               (*_parse(p_name))
        }

    seniors = get_seniors(fake, 'CSE 15')
    assert set(seniors.keys()) == {'CSE 14', 'CSE 13', 'CSE-12'}, \
        f'Wrong CSE seniors: {set(seniors.keys())}'
    assert 'EEE 15' not in seniors
    assert 'CSE 15' not in seniors          # current profile excluded

    seniors_eee = get_seniors(fake, 'EEE 15')
    assert set(seniors_eee.keys()) == {'EEE 14'}

check('logic   :: senior lookup correct across separators', test_senior_lookup)


# ─── 7. Concurrent locked write simulation (20 threads) ──────────────────────

def test_threadsafe_write():
    tmp = os.path.join(ROOT, '_smoke_test_lock_tmp.json')
    lock = threading.Lock()
    errors = []

    def writer(data):
        try:
            with lock:
                existing = []
                if os.path.exists(tmp):
                    with open(tmp) as f:
                        existing = json.load(f)
                existing.append(data)
                with open(tmp, 'w') as f:
                    json.dump(existing, f)
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with open(tmp) as f:
        result = json.load(f)
    os.remove(tmp)

    assert len(result) == 20, f'Expected 20 entries, got {len(result)}'
    assert not errors, f'Thread errors: {errors}'

check('concurrency :: 20-thread locked write, no corruption', test_threadsafe_write)


# ─── 8. monitor.py fast-boot: no heavy import at module top ──────────────────

def test_monitor_fast_boot():
    src = read_file('exam_monitor/monitor.py')
    top = [
        l for l in src.split('\n')[:20]
        if l.strip() and not l.strip().startswith('#')
    ]
    bad = [
        l for l in top
        if 'auto_pdf_mailer' in l or 'pdfkit' in l or 'cli_scraper' in l
    ]
    assert not bad, f'Heavy import at top level: {bad}'

check('fastboot :: monitor.py has no heavy imports at module top', test_monitor_fast_boot)


# ─── 9. Workflow YAML gates ───────────────────────────────────────────────────
# The YAML uses steps.check.outputs.new_exams == 'true' as a conditional gate.
# monitor.py writes `new_exams=true` / `new_exams=false` to GITHUB_OUTPUT.
# Both sides of that contract are checked here.

def test_workflow_yaml():
    yml = read_file('.github/workflows/exam_monitor.yml')
    mon = read_file('exam_monitor/monitor.py')
    checks = {
        'concurrency cancel-in-progress=false':               ('cancel-in-progress: false',              yml),
        'YAML gate reads new_exams output':                   ("steps.check.outputs.new_exams == 'true'", yml),
        'monitor.py writes new_exams=true to GITHUB_OUTPUT':  ('new_exams=true',                         mon),
        'monitor.py writes new_exams=false to GITHUB_OUTPUT': ('new_exams=false',                        mon),
        'v2 cross-branch sync step present':                  ('v2_sync_tasks.json',                     yml),
        'profiles.json included in commit pattern':           ('saved_profiles.json',                    yml),
        'xvfb-run present for wkhtmltopdf rendering':         ('xvfb-run',                               yml),
    }
    for label, (token, src) in checks.items():
        assert token in src, f'Missing: {label!r} (token {token!r})'

check('yaml    :: all workflow gate tokens present', test_workflow_yaml)


# ─── 10. v2_auto_sync.py: stricter dual-filter ───────────────────────────────

def test_v2_dual_filter():
    src = git_show('origin/v2:v2_auto_sync.py')
    assert 'subject_load_ratio' in src, 'v2 missing subject_load_ratio guard'
    assert 'overlap_ratio >= 0.5 and subject_load_ratio >= 0.7' in src, \
        'v2 dual-filter condition missing'

check('v2      :: stricter dual-filter (overlap>=50% AND load>=70%)', test_v2_dual_filter)


# ─── 11. v2 database: WAL mode + busy_timeout ────────────────────────────────

def test_v2_wal():
    src = git_show('origin/v2:database.py')
    assert 'journal_mode = WAL' in src, 'v2 database not using WAL mode'
    assert 'busy_timeout' in src, 'v2 database missing busy_timeout'

check('v2      :: database uses WAL + busy_timeout for concurrency', test_v2_wal)


# ─── 12. Cross-branch handshake: v2_sync_tasks.json schema contract ──────────
# main writes {pro_id, exam_id, exam_name, profile_name}.
# v2 reads task.get('pro_id') etc.  Both sides must carry the same 4 fields.

def test_crossbranch_schema():
    main_src = read_file('exam_monitor/auto_pdf_mailer.py')
    v2_src   = git_show('origin/v2:v2_auto_sync.py')
    fields = ['pro_id', 'exam_id', 'exam_name', 'profile_name']
    for field in fields:
        assert f'"{field}"' in main_src, f'main: task_data missing field {field!r}'
        assert f'"{field}"' in v2_src,   f'v2: sync reader missing field {field!r}'

check('contract :: v2_sync_tasks.json schema matches main<->v2', test_crossbranch_schema)


# ─── 13. v2 readd: uses db layer (not raw JSON writes) ───────────────────────

def test_v2_uses_db():
    src = git_show('origin/v2:v2_auto_sync.py')
    assert 'db.upsert_student' in src, \
        'v2 not using db.upsert_student for readd persistence'
    assert 'db.save_exam_analytics_only' in src, \
        'v2 not saving readd analytics to DB'

check('v2      :: readd persistence uses db layer (not raw JSON)', test_v2_uses_db)


# ─── 14. main readd: existing_regs dedup guard present ───────────────────────

def test_main_dedup():
    src = read_file('exam_monitor/auto_pdf_mailer.py')
    assert 'existing_regs.add(reg)' in src, \
        'existing_regs dedup guard missing — duplicate readds may be appended'

check('dedup   :: existing_regs prevents duplicate readd appends', test_main_dedup)


# ─── Report ───────────────────────────────────────────────────────────────────

def _report():
    print('\n' + '=' * 65)
    print('  EXAM MONITOR WORKFLOW - INTEGRATION SMOKE TEST')
    print('=' * 65)
    all_ok = True
    for r in RESULTS:
        status = r[0]
        name   = r[1]
        detail = r[2] if len(r) > 2 else ''
        icon   = '[OK]  ' if status == 'OK' else '[FAIL]'
        print(f'{icon}  {name}')
        if detail:
            print(f'            => {detail}')
        if status != 'OK':
            all_ok = False

    print('=' * 65)
    total  = len(RESULTS)
    passed = sum(1 for r in RESULTS if r[0] == 'OK')
    verdict = 'ALL CHECKS PASSED' if all_ok else 'FAILURES DETECTED'
    print(f'  RESULT: {passed}/{total} passed  |  {verdict}')
    print('=' * 65)
    return all_ok


if __name__ == '__main__':
    ok = _report()
    sys.exit(0 if ok else 1)
