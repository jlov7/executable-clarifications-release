"""Real HTTP export journey; authored policies and reviewed local implementation only."""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from executable_clarifications.examples import ExampleSet
from executable_clarifications.session import canonical, render_contract


def run(root, baseline=False):
    mode = os.environ.get('BROWSER_TEST_MODE', 'http')
    if mode not in ('http', 'inline'): raise ValueError('unknown browser delivery mode')
    evidence = Path(os.environ.get('BROWSER_EVIDENCE_DIR', root/'.release-scratch/export-target'))
    evidence.mkdir(parents=True, exist_ok=True)
    scratch = root/'.release-scratch'
    scratch.mkdir(exist_ok=True)
    spec = {'schema': 'executable-clarifications/example-set-v1',
            'fields': {'days': 'integer', 'priority': 'boolean'},
            'examples': [{'id': 'ordinary_boundary', 'input': {'days': 30, 'priority': False}, 'expected': True},
                         {'id': 'ordinary_expired', 'input': {'days': 31, 'priority': False}, 'expected': False},
                         {'id': 'priority_exception', 'input': {'days': 35, 'priority': True}, 'expected': True},
                         {'id': 'exception_expired', 'input': {'days': 46, 'priority': True}, 'expected': False}]}
    policy = {'schema': 'executable-clarifications/policy-v1', 'fields': spec['fields'],
              'candidates': [{'id': 'ordinary_only', 'rule': {'field': 'days', 'op': '<=', 'value': 30}},
                             {'id': 'all_45', 'rule': {'field': 'days', 'op': '<=', 'value': 45}}],
              'cases': [{'id': row['id'], 'input': row['input']} for row in spec['examples']]}
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    stderr_path = evidence/f'export-target-server-{os.getpid()}.stderr'
    stderr_log = stderr_path.open('wb')
    try:
        server = subprocess.Popen([sys.executable, str(root/'scripts/serve_session_demo.py'), '--port', str(port)],
                                  cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except BaseException:
        stderr_log.close()
        raise
    stderr_state = {'bytes_seen': 0, 'bytes_retained': 0, 'limit': 262144}
    def capture_stderr():
        while chunk := os.read(server.stderr.fileno(), 4096):
            stderr_state['bytes_seen'] += len(chunk)
            retained = chunk[:max(0, stderr_state['limit']-stderr_state['bytes_retained'])]
            stderr_log.write(retained); stderr_log.flush()
            stderr_state['bytes_retained'] += len(retained)
    stderr_thread = threading.Thread(target=capture_stderr, daemon=True)
    stderr_thread.start()
    started = time.monotonic()
    navigation, omitted = [], 0
    def note(event, **fields):
        nonlocal omitted
        if len(navigation) < 512:
            navigation.append({'event': event, 'seconds': round(time.monotonic()-started, 3), **fields})
        else: omitted += 1
    def navigate(page, label, url):
        note('navigation-start', page=label, target=url)
        try:
            response = page.goto(url)
            note('navigation-complete', page=label, url=page.url, status=response.status if response else None)
        except Exception as error:
            note('navigation-failed', page=label, url=page.url, error=str(error))
            raise
    def observe(page, label):
        page.on('domcontentloaded', lambda: note('domcontentloaded', page=label, url=page.url))
        page.on('load', lambda: note('load', page=label, url=page.url))
    checks, errors, external = [], [], []
    try:
        import selectors
        selector = selectors.DefaultSelector(); selector.register(server.stdout, selectors.EVENT_READ)
        try:
            if not selector.select(15):
                raise RuntimeError('documented local server did not become ready')
            announced = server.stdout.readline().strip()
        finally: selector.close()
        url = f'http://127.0.0.1:{port}/session.html'
        assert announced == url, announced
        note('server-announced', url=url, pid=server.pid)
        with (evidence/'servers.jsonl').open('a') as stream:
            stream.write(json.dumps({'event': 'bound', 'pid': server.pid, 'host': '127.0.0.1',
                                     'port': port, 'script': Path(__file__).name})+'\n')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_PATH'))
            try:
                for width, height in ((1280, 900), (390, 844)):
                    context = browser.new_context(accept_downloads=True, viewport={'width': width, 'height': height})
                    page = context.new_page(); page.set_default_timeout(5000); prefix = f'http://127.0.0.1:{port}/'
                    context.route('**/*', lambda route, _request, prefix=prefix: route.continue_() if route.request.url.startswith(prefix)
                                  else (external.append(route.request.url), route.abort()))
                    context.on('request', lambda request, width=width: note('request', width=width, url=request.url))
                    context.on('response', lambda response, width=width: note('response', width=width, url=response.url, status=response.status))
                    context.on('requestfailed', lambda request, width=width: note('requestfailed', width=width, url=request.url, failure=request.failure))
                    observe(page, f'main-{width}')
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
                    page.on('dialog', lambda dialog: dialog.accept())
                    if mode == 'http':
                        navigate(page, f'main-{width}', url)
                        assert page.evaluate('isSecureContext && !!crypto.subtle && crypto.subtle.digest.toString().includes("[native code]")')
                    else:
                        # Inspect owned assets without changing browser navigation policy.
                        html = (root/'web/session.html').read_text()
                        scripts = re.findall(r'<script src="([^"]+)"></script>', html)
                        html = re.sub(r'<script src="[^"]+"></script>', '', html)
                        html = re.sub(r'<link rel="stylesheet"[^>]*>', '', html)
                        page.set_content(html)
                        page.add_style_tag(content=(root/'web/styles.css').read_text())
                        for script in scripts:
                            asset = (root/'web'/script).resolve()
                            assert asset.is_relative_to((root/'web').resolve())
                            page.add_script_tag(content=asset.read_text())
                    page.get_by_role('button', name='Start from known examples', exact=True).click()
                    def upload(data, target='#examples-file', page=page):
                        page.set_input_files(target, {'name': 'owned-policy.json', 'mimeType': 'application/json',
                                                     'buffer': canonical(data).encode()})
                    upload(spec)
                    try:
                        page.locator('#examples-confirm').click()
                    except Exception:
                        (evidence/f'failed-{width}.json').write_text(json.dumps({'errors': errors, 'message': page.locator('#examples-error').text_content(), 'secure': page.evaluate('({secure:isSecureContext,subtle:!!crypto.subtle})')}))
                        raise
                    record = json.loads(page.locator('#examples-record').text_content())
                    expected = ExampleSet(spec); expected.confirm()
                    assert record == expected.export_record()
                    # The incomplete candidate set cannot overrule explicit examples.
                    upload(policy, '#examples-audit-file')
                    page.locator('#examples-audit-confirm').check()
                    page.locator('#examples-explain').click()
                    page.locator('#examples-explanation').wait_for(state='visible')
                    explanation = json.loads(page.locator('#examples-explanation-json').text_content())
                    assert explanation['status'] == 'NO_OFFERED_CANDIDATE_FITS'
                    assert not explanation['labels_judged_incorrect']
                    target = 'service_policy:eligible'
                    if baseline:
                        assert page.locator('#examples-target').count() == 0
                    else:
                        field = page.get_by_label('Known-example test target (module:function)', exact=True)
                        for invalid in ('', 'os:system()', 'service_policy:class', 'service/policy:eligible'):
                            field.fill(invalid)
                            assert page.locator('#examples-export').is_disabled()
                            assert field.get_attribute('aria-invalid') == 'true'
                        field.fill(target)
                        assert field.get_attribute('aria-invalid') == 'false'
                        assert json.loads(page.locator('#examples-record').text_content()) == record
                        page.locator('#examples-edit').click()
                        page.get_by_label('days', exact=True).first.fill('29')
                        page.keyboard.press('Tab')
                        edited_target = 'other_policy:allow'
                        field.fill(edited_target)
                        assert page.locator('#examples-export').is_disabled()
                        page.locator('#examples-cancel').click()
                        assert field.input_value() == edited_target
                        assert json.loads(page.locator('#examples-record').text_content()) == record
                        with page.expect_download() as event: page.locator('#examples-export').click()
                        cancelled = evidence/f'test_cancelled_{width}.py'; event.value.save_as(cancelled)
                        assert cancelled.read_text() == render_contract(expected, edited_target)
                        field.fill(target)
                    with page.expect_download() as event:
                        page.locator('#examples-export').focus(); page.keyboard.press('Enter')
                    export = evidence/f'test_export_{width}.py'; event.value.save_as(export)
                    source = export.read_text()
                    actual_target = 'implementation:decide' if baseline else target
                    assert source == render_contract(expected, actual_target)
                    with tempfile.TemporaryDirectory(dir=scratch, prefix='export-target-') as directory:
                        work = Path(directory)
                        (work/'test_contract.py').write_text(source)
                        implementation = work/'service_policy.py'
                        implementation.write_text('def eligible(x):\n    return x["days"] <= (45 if x["priority"] else 30)\n')
                        good = subprocess.run([sys.executable, 'test_contract.py'], cwd=work,
                                              capture_output=True, text=True, timeout=10, check=False)
                        assert (good.returncode != 0) if baseline else (good.returncode == 0), good.stderr
                        implementation.write_text('def eligible(x):\n    return x["days"] <= 30\n')
                        # Avoid a same-size/same-second Python bytecode cache hit.
                        import shutil
                        shutil.rmtree(work/'__pycache__', ignore_errors=True)
                        bad = subprocess.run([sys.executable, 'test_contract.py'], cwd=work,
                                             capture_output=True, text=True, timeout=10, check=False)
                        assert bad.returncode != 0
                    if not baseline:
                        assert 'priority_exception' in bad.stderr
                        with page.expect_download() as event: page.locator('#examples-save').click()
                        saved = evidence/f'review_{width}.json'; event.value.save_as(saved)
                        assert json.loads(saved.read_text()) == record
                        upload(record)
                        expect(page.locator('#examples-confirm')).to_be_enabled()
                        assert page.locator('#examples-export').is_disabled()
                        page.locator('#examples-confirm').click()
                        assert page.get_by_label('Known-example test target (module:function)', exact=True).input_value() == target
                        # A changed requirement invalidates confirmation, not the target grammar.
                        revised = json.loads(json.dumps(spec)); revised['examples'][1]['expected'] = True
                        upload(revised)
                        expect(page.locator('#examples-confirm')).to_be_enabled()
                        assert page.locator('#examples-export').is_disabled()
                        page.locator('#examples-confirm').click()
                        changed = ExampleSet(revised); changed.confirm()
                        with page.expect_download() as event: page.locator('#examples-export').click()
                        revised_path = evidence/f'test_revised_{width}.py'; event.value.save_as(revised_path)
                        assert revised_path.read_text() == render_contract(changed, target)
                        assert changed.export_record()['version_digest'] != record['version_digest']
                        fresh = context.new_page()
                        fresh.set_default_timeout(5000)
                        fresh.on('dialog', lambda dialog: dialog.accept())
                        fresh.on('pageerror', lambda error: errors.append(str(error)))
                        fresh.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
                        observe(fresh, f'fresh-{width}')
                        navigate(fresh, f'fresh-{width}', url)
                        assert fresh.locator('#examples-target').input_value() == 'implementation:decide'
                        assert fresh.locator('#examples-export').is_disabled()
                        fresh.get_by_role('button', name='Start from known examples', exact=True).click()
                        fresh.set_input_files('#examples-file', {'name': 'saved-review.json', 'mimeType': 'application/json',
                                                               'buffer': canonical(record).encode()})
                        expect(fresh.locator('#examples-confirm')).to_be_enabled()
                        assert fresh.locator('#examples-export').is_disabled()
                        fresh.locator('#examples-confirm').click()
                        assert fresh.locator('#examples-target').input_value() == 'implementation:decide'
                        assert json.loads(fresh.locator('#examples-record').text_content()) == record
                        with fresh.expect_download() as event: fresh.locator('#examples-export').click()
                        reset = evidence/f'test_fresh_tab_{width}.py'; event.value.save_as(reset)
                        assert reset.read_text() == render_contract(expected, 'implementation:decide')
                        fresh.screenshot(path=str(evidence/f'export-target-default-{width}.png'), full_page=True)
                        fresh.close()
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                    page.screenshot(path=str(evidence/f'export-target-{width}.png'), full_page=True)
                    checks.append({'width': width, 'delivery_mode': mode, 'candidate_gap_retained': True,
                                   'export_equals_python': True, 'reviewed_custom_target_passes': not baseline,
                                   'edit_cancel_preserves_review_and_target': not baseline,
                                   'fresh_tab_resets_target_without_changing_review': not baseline,
                                   'native_webcrypto': mode == 'http',
                                   'wrong_implementation_rejected': True})
                    context.close()
            finally:
                browser.close()
        assert not errors and not external, (errors, external)
        return {'mode': 'baseline' if baseline else 'candidate', 'checks': checks,
                'console_errors': errors, 'external_requests': external,
                'human_usability': 'NOT RUN; automated Chromium with authored cases'}
    finally:
        server.terminate()
        try: server.wait(timeout=5)
        except subprocess.TimeoutExpired: server.kill(); server.wait(timeout=5)
        stderr_thread.join(timeout=5)
        server.stdout.close(); server.stderr.close(); stderr_log.close()
        (evidence/f'export-target-diagnostics-{os.getpid()}.json').write_text(json.dumps({
            'navigation': navigation, 'events_omitted': omitted,
            'server': {'pid': server.pid, 'exit_code': server.returncode, 'stderr': str(stderr_path),
                       **stderr_state, 'capture_thread_alive': stderr_thread.is_alive()}}, indent=2)+'\n')
        with (evidence/'servers.jsonl').open('a') as stream:
            stream.write(json.dumps({'event': 'closed', 'pid': server.pid, 'host': '127.0.0.1',
                                     'port': port, 'script': Path(__file__).name})+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(run(args.root.resolve(), args.baseline), indent=2))
