"""Actual Chromium checks; separate from the stdlib core tests. No model calls.

Requires playwright and a Chromium installation. Set CHROMIUM_PATH only to a
trusted local binary. Screenshots are optional and written outside repository source.
"""
import json
import os
import re
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from build_session_demo import verify_assets
from playwright.sync_api import sync_playwright

from executable_clarifications.policy import PolicySession
from executable_clarifications.session import Session, render_contract


def run():
    mode = os.environ.get('BROWSER_TEST_MODE', 'http')
    if mode not in ('http', 'inline'): raise ValueError('BROWSER_TEST_MODE must be http or inline')
    web = Path(__file__).resolve().parents[1] / 'web'
    verify_assets()
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(web)))
    def lifecycle(event):
        if os.environ.get('BROWSER_EVIDENCE_DIR'):
            out = Path(os.environ['BROWSER_EVIDENCE_DIR']); out.mkdir(parents=True, exist_ok=True)
            with (out / 'servers.jsonl').open('a') as stream:
                stream.write(json.dumps({'event': event, 'pid': os.getpid(), 'host': '127.0.0.1',
                                         'port': server.server_port, 'script': Path(__file__).name}) + '\n')
    lifecycle('bound')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors, blocked, checks = [], [], []
    try:
        with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmp:
            kwargs = {'headless': True}
            if os.environ.get('CHROMIUM_PATH'):
                kwargs['executable_path'] = os.environ['CHROMIUM_PATH']
            browser = pw.chromium.launch(**kwargs)
            context = browser.new_context(viewport={'width': 1280, 'height': 900}, accept_downloads=True)
            page = context.new_page()
            page.on('dialog', lambda dialog: dialog.accept());page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
            prefix = f'http://127.0.0.1:{server.server_port}/'
            def route(request):
                if request.request.url.startswith(prefix): request.continue_()
                else: blocked.append(request.request.url); request.abort()
            context.route('**/*', route)
            def navigate(filename):
                if mode == 'http':
                    page.goto(prefix + filename)
                    return
                # Render owned local assets in-memory when HTTP navigation is unavailable.
                # This does not test HTTP delivery and does not change browser policy.
                html = (web / filename).read_text()
                scripts = re.findall(r'<script src="([^"]+)"></script>', html)
                html = re.sub(r'<script src="[^"]+"></script>', '', html)
                html = re.sub(r'<link rel="stylesheet"[^>]*>', '', html)
                page.set_content(html)
                page.add_style_tag(content=(web / 'styles.css').read_text())
                for script in scripts:
                    page.add_script_tag(content=(web / script).read_text())
            navigate('session.html')
            page.wait_for_function('window.CLARIFICATION_CASES && document.querySelector("#scenario").options.length === 3')
            assert page.title() == 'Executable Clarifications: adaptive sessions'
            assert page.locator('h1').inner_text().startswith('Choose behavior.')
            for scenario in ('orders', 'batch', 'response'):
                page.select_option('#scenario', scenario)
                assert page.locator('#download-test').is_disabled()
                assert 'synthetic examples' in page.locator('#provenance-note').inner_text()
                assert page.locator('#remaining').inner_text() == 'This case separates 4 remaining rules.'
                assert page.locator('#interpretations tr').count() == 4
                assert page.locator('#interpretations td').count() == 12
                assert 'what should the output be?' in page.locator('#question').inner_text()
                page.click('#answer-true')
                assert page.locator('#question').evaluate('(element) => element === document.activeElement')
                assert page.locator('#interpretations tr').count() == 2
                page.click('#answer-false')
                assert 'CANDIDATE_SET_NARROWED' in page.locator('#status').inner_text()
                record = json.loads(page.locator('#record').text_content())
                restored = Session.from_record(record)
                assert len(restored.examples()) == 2
                assert page.locator('#outcome').is_visible(), 'completed session hides the remaining rule'
                expected_rules = [f'{c["id"]}: {c["field"]} {c["operator"]} {c["threshold"]}'
                                  for c in record['candidates'] if c['id'] in restored.remaining_ids]
                assert page.locator('#remaining-rules li').all_text_contents() == expected_rules
                assert page.locator('#answer-history li').count() == 2
                for example, line in zip(restored.examples(), page.locator('#answer-history li').all_text_contents()):
                    field, value = next(iter(example['input'].items()))
                    assert line == f'{field} = {value}: {str(example["expected"]).lower()}'
                page.click('#undo')
                assert len(json.loads(page.locator('#record').text_content())['decisions']) == 1
                assert page.locator('#outcome').is_hidden()
                assert page.locator('#question').evaluate('(element) => element === document.activeElement')
                page.click('#answer-false')
                with page.expect_download() as pending:
                    page.click('#download-test')
                downloaded = pending.value
                target = Path(tmp) / f'{scenario}.py'
                downloaded.save_as(target)
                assert target.read_text() == render_contract(restored, 'implementation:decide')
                page.click('#reset')
                page.click('#answer-neither')
                assert 'UNRESOLVED' in page.locator('#status').inner_text()
                assert page.locator('#download-test').is_disabled()
                assert page.locator('#question-panel').is_hidden()
                assert page.locator('#outcome-title').inner_text() == 'No rule chosen'
                assert 'neither' in page.locator('#answer-history').inner_text()
                page.click('#undo')
                assert page.locator('#answer-history li').count() == 0
                assert page.locator('#undo').is_disabled()
                assert page.locator('#question-panel').is_visible()
                checks.append(scenario + ': visible completion rules / answer history / undo and neither recovery')
                checks.append(scenario + ': adaptive path / identical Python export / neither blocked')
            page.locator('details').filter(has=page.locator('#record')).locator('summary').click()
            assert page.locator('#record').is_visible()
            page.locator('details').filter(has=page.locator('#record')).locator('summary').click()
            checks.append('inspectable collapsible JSON')
            page.click('#reset')
            page.focus('#answer-true')
            page.keyboard.press('Enter')
            assert len(json.loads(page.locator('#record').text_content())['decisions']) == 1
            assert page.locator('#question').evaluate('(element) => element === document.activeElement')
            page.keyboard.press('Tab')
            assert page.locator('#answer-true').evaluate('(element) => element === document.activeElement')
            assert page.locator('#status').get_attribute('role') == 'status'
            assert page.locator('#answer-true').get_attribute('aria-describedby') == 'true-group'
            checks.append('keyboard activation / next-question focus / descriptions / live status')
            out = os.environ.get('BROWSER_EVIDENCE_DIR')
            for width, height in [(1280,900),(390,844)]:
                page.set_viewport_size({'width':width, 'height':height})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                assert page.locator('#answer-true').is_visible()
                page.click('#reset')
                page.click('#answer-true')
                assert page.locator('#question').evaluate('(element) => element === document.activeElement')
                page.click('#answer-false')
                assert 'CANDIDATE_SET_NARROWED' in page.locator('#status').inner_text()
                page.click('#reset')
                page.click('#answer-neither')
                assert page.locator('#download-test').is_disabled()
                page.click('#reset')
                if out:
                    Path(out).mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(Path(out) / f'clarifications-session-{width}.png'), full_page=True)
                checks.append(f'adaptive path / neither / visible controls / no overflow {width}x{height}')
            # User-supplied multi-field policy, persistence and hostile local import checks.
            policy = json.loads((web / 'refund-policy.json').read_text())
            def upload(value, name='policy.json', reject=False):
                page.set_input_files('#policy-file', {'name': name, 'mimeType': 'application/json',
                    'buffer': (value if isinstance(value, str) else json.dumps(value)).encode()})
                page.wait_for_function("document.querySelector('#policy-file').value === '' && document.querySelector('#import-status').textContent.startsWith(" +
                                       json.dumps('Import rejected:' if reject else 'Imported locally:') + ")")
            for width, height in [(1280,900), (390,844)]:
                page.set_viewport_size({'width': width, 'height': height})
                upload(policy)
                assert page.locator('#provenance-note').inner_text() == 'Rules and cases come from your reviewed local policy. No model calls or external services are used.'
                assert page.locator('#remaining').inner_text() == 'This case separates 4 remaining rules.'
                assert 'days' in page.locator('#question').inner_text()
                assert 'unopened' in page.locator('#question').inner_text()
                assert 'reason' in page.locator('#question').inner_text()
                original = json.loads(page.locator('#record').text_content())
                page.click('#answer-neither')
                assert page.locator('#download-test').is_disabled()
                assert 'Undo' in page.locator('#outcome-help').inner_text()
                page.click('#undo')
                assert json.loads(page.locator('#record').text_content()) == original
                session = PolicySession.from_record(original)
                q = session.question(); x = q['input']
                answer = (x['days'] <= 30 and x['unopened']) or x['reason'] == 'defective'
                page.click('#answer-' + str(answer).lower())
                with page.expect_download() as pending:
                    page.click('#download-record')
                saved = Path(tmp) / f'custom-session-{width}.json'
                pending.value.save_as(saved)
                expected = json.loads(saved.read_text())
                page.reload(); page.wait_for_selector('#scenario option', state='attached')
                upload(expected, 'resume.json')
                assert json.loads(page.locator('#record').text_content()) == expected
                while page.locator('#question-panel').is_visible():
                    session = PolicySession.from_record(json.loads(page.locator('#record').text_content()))
                    x = session.question()['input']
                    answer = (x['days'] <= 30 and x['unopened']) or x['reason'] == 'defective'
                    page.click('#answer-' + str(answer).lower())
                record = json.loads(page.locator('#record').text_content())
                session = PolicySession.from_record(record)
                assert session.remaining_ids == ('refund',)
                assert 'refund:' in page.locator('#remaining-rules').inner_text()
                assert page.locator('#answer-history li').count() == len(session.examples())
                with page.expect_download() as pending: page.click('#download-test')
                exported = Path(tmp) / f'custom-contract-{width}.py'
                pending.value.save_as(exported)
                assert exported.read_text() == render_contract(session, 'implementation:decide')
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                if out:
                    page.screenshot(path=str(Path(out) / f'custom-policy-complete-{width}.png'), full_page=True)
                bad_record = json.loads(json.dumps(record)); bad_record['policy']['cases'][0]['input']['days'] = 99
                bad_history = json.loads(json.dumps(record)); bad_history['decisions'][0]['question_id'] = 'tampered'
                xss = json.loads(json.dumps(policy)); xss['cases'][0]['input']['reason'] = '<img src=x onerror=alert(1)>'
                for invalid in [bad_record, bad_history, xss, '{', '{"schema":1,"schema":2}',
                                dict(policy, unknown=True), dict(policy, fields={'__proto__':'boolean'})]:
                    upload(invalid, 'invalid.json', reject=True)
                    assert json.loads(page.locator('#record').text_content()) == record
                    assert page.locator('img').count() == 0
                page.click('#undo')
                assert page.locator('#question-panel').is_visible()
                assert page.locator('#question').evaluate('(element) => element === document.activeElement')
                if out:
                    page.screenshot(path=str(Path(out) / f'custom-policy-review-{width}.png'), full_page=True)
                checks.append(f'custom multi-field {width}: import / neither / undo / download / reload / resume / exact contract / completion / tamper and XSS rejection')
            # Long allowed identifiers/values must remain readable without horizontal overflow.
            long_policy = json.loads(json.dumps(policy))
            rename = {name: name + '_' * (64 - len(name)) for name in policy['fields']}
            long_policy['fields'] = {rename[k]: v for k,v in policy['fields'].items()}
            def rename_rule(rule):
                if 'field' in rule: rule['field'] = rename[rule['field']]
                else:
                    for child in next(iter(rule.values())): rename_rule(child)
            for c in long_policy['candidates']:
                c['id'] += '_' * (64 - len(c['id'])); rename_rule(c['rule'])
            for case in long_policy['cases']:
                case['id'] += '_' * (64 - len(case['id']))
                case['input'] = {rename[k]: v for k,v in case['input'].items()}
            page.set_viewport_size({'width':390,'height':844})
            upload(long_policy)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            while page.locator('#question-panel').is_visible():
                session = PolicySession.from_record(json.loads(page.locator('#record').text_content()))
                q = session.question()
                answer = q['outputs']['refund' + '_' * 58]
                page.click('#answer-' + str(answer).lower())
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert ('refund' + '_' * 58) in page.locator('#remaining-rules').inner_text()
            if out:
                page.screenshot(path=str(Path(out) / 'custom-long-policy-390.png'), full_page=True)
            checks.append('custom long identifiers: all fields and surviving rules visible with no mobile overflow')
            # Every accepted policy must survive an explicit download/reimport roundtrip.
            leaf = {'field':'x','op':'>','value':0}
            wide = {'and': [{'or': [leaf] * 6} for _ in range(16)]}
            deep = leaf
            for _ in range(6): deep = {'or':[deep,leaf]}
            roundtrip_failures = []
            for label, rule, count in [('near-byte-limit', wide, 32), ('max-rule-depth', deep, 2)]:
                boundary_policy = {'schema':'executable-clarifications/policy-v1',
                    'fields':{'x':'integer'},
                    'candidates':[{'id':f'candidate_{i:02d}','rule':rule} for i in range(count)],
                    'cases':[{'id':'one','input':{'x':1}}]}
                content = json.dumps(boundary_policy, sort_keys=True, separators=(',',':'))
                assert len(content.encode()) <= 131072
                upload(content, label + '.json')
                expected = json.loads(page.locator('#record').text_content())
                with page.expect_download() as pending: page.click('#download-record')
                saved = Path(tmp) / (label + '-session.json')
                pending.value.save_as(saved)
                saved_bytes = saved.read_bytes()
                page.reload(); page.wait_for_selector('#scenario option', state='attached')
                page.set_input_files('#policy-file', {'name':saved.name,
                    'mimeType':'application/json','buffer':saved_bytes})
                page.wait_for_function("document.querySelector('#policy-file').value === '' && (document.querySelector('#import-status').textContent.startsWith('Imported locally:') || document.querySelector('#import-status').textContent.startsWith('Import rejected:'))")
                status = page.locator('#import-status').inner_text()
                if not status.startswith('Imported locally:'):
                    roundtrip_failures.append({'policy':label,'policy_bytes':len(content.encode()),
                        'saved_bytes':len(saved_bytes),'status':status})
                    continue
                assert len(saved_bytes) <= 262144
                assert json.loads(page.locator('#record').text_content()) == expected
                restored = PolicySession.from_record(json.loads(saved_bytes))
                assert restored.export_record() == expected
                assert page.locator('#remaining-rules li').count() == count
                if out:
                    (Path(out) / (label + '-policy.json')).write_text(content)
                    (Path(out) / (label + '-downloaded-session.json')).write_bytes(saved_bytes)
                checks.append(f'{label}: policy {len(content.encode())} bytes / saved {len(saved_bytes)} bytes / browser download and reimport / Python replay identical')
            assert not roundtrip_failures, roundtrip_failures
            # The starter UI remains usable too.
            navigate('index.html')
            page.click('#inclusive')
            assert json.loads(page.locator('#artifact').inner_text())['expected'] is True
            checks.append('original UI regression')
            context.close(); browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3); lifecycle('closed')
    assert not errors, errors
    assert not blocked, blocked
    return {'delivery_mode': mode, 'checks': checks, 'console_errors': errors, 'external_requests': blocked,
            'boundary': 'Chromium only; authored examples, no human-comprehension study.'}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
