import os
import sys
import json
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = []

def check(label, fn):
    try:
        fn()
        RESULTS.append(('OK', label))
    except AssertionError as e:
        RESULTS.append(('FAIL', label, str(e)))
    except Exception as e:
        RESULTS.append(('ERROR', label, f"{type(e).__name__}: {e}"))

def read_file(rel):
    path = os.path.join(ROOT, rel)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

# 1. Fastboot: monitor.py has no heavy imports at module top
def test_monitor_fast_boot():
    src = read_file('exam_monitor/monitor.py')
    top = [l for l in src.split('\n')[:25] if l.strip() and not l.strip().startswith('#')]
    bad = [l for l in top if 'auto_pdf_mailer' in l or 'pdfkit' in l or 'cli_scraper' in l]
    assert not bad, f'Heavy import at top level: {bad}'

check('fastboot :: monitor.py has no heavy imports at module top', test_monitor_fast_boot)

# 2. Concurrency: threadsafe locked write simulation
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

# 3. Cross-branch handshake: v2_sync_tasks.json schema contract
def test_crossbranch_schema():
    main_src = read_file('exam_monitor/auto_pdf_mailer.py')
    v2_src = read_file('v2_auto_sync.py')
    fields = ['pro_id', 'exam_id', 'exam_name', 'profile_name']
    for field in fields:
        assert f'"{field}"' in main_src, f'auto_pdf_mailer.py missing field {field!r}'
        assert f'"{field}"' in v2_src, f'v2_auto_sync.py missing field {field!r}'

check('contract :: v2_sync_tasks.json schema matches auto_pdf_mailer<->v2_auto_sync', test_crossbranch_schema)

# 4. Sync file path matching
def test_sync_file_path():
    main_src = read_file('exam_monitor/auto_pdf_mailer.py')
    assert 'v2_sync_tasks.json' in main_src, 'auto_pdf_mailer missing v2_sync_tasks.json'
    assert 'repo_root' in main_src, 'auto_pdf_mailer should write to repo_root for GitHub Actions step'

check('filepath :: auto_pdf_mailer writes v2_sync_tasks.json in repo root for Actions step', test_sync_file_path)

# 5. Hybrid profile fallback in auto_pdf_mailer.py
def test_hybrid_profiles():
    main_src = read_file('exam_monitor/auto_pdf_mailer.py')
    assert 'saved_profiles.json' in main_src, 'auto_pdf_mailer missing saved_profiles.json support for main branch'
    assert 'db.get_profiles()' in main_src, 'auto_pdf_mailer missing db.get_profiles() fallback for v2 branch'

check('hybrid   :: auto_pdf_mailer supports both saved_profiles.json and db.get_profiles', test_hybrid_profiles)

def _report():
    print('\n' + '=' * 65)
    print('  EXAM MONITOR WORKFLOW - INTEGRATION SMOKE TEST')
    print('=' * 65)
    all_ok = True
    for r in RESULTS:
        status, name = r[0], r[1]
        detail = r[2] if len(r) > 2 else ''
        icon = '[OK]  ' if status == 'OK' else '[FAIL]'
        print(f'{icon}  {name}')
        if detail:
            print(f'            => {detail}')
        if status != 'OK':
            all_ok = False

    print('=' * 65)
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r[0] == 'OK')
    verdict = 'ALL CHECKS PASSED' if all_ok else 'FAILURES DETECTED'
    print(f'  RESULT: {passed}/{total} passed  |  {verdict}')
    print('=' * 65)
    return all_ok

if __name__ == '__main__':
    ok = _report()
    sys.exit(0 if ok else 1)
