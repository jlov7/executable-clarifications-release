"""Authored boundary/exception review journey over literal loopback only."""
import json
import os
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from executable_clarifications.policy import PolicySession
from executable_clarifications.session import canonical, render_contract


def run():
    root = Path(__file__).resolve().parents[1]
    evidence = Path(os.environ.get('BROWSER_EVIDENCE_DIR', root / '.release-scratch/browser'))
    evidence.mkdir(parents=True, exist_ok=True)
    scratch = root / '.release-scratch'; scratch.mkdir(exist_ok=True)
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(root / 'web')))
    def lifecycle(event):
        with (evidence / 'servers.jsonl').open('a') as stream:
            stream.write(json.dumps({'event': event, 'pid': os.getpid(), 'host': '127.0.0.1',
                                     'port': server.server_port, 'script': Path(__file__).name}) + '\n')
    lifecycle('bound')
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    errors, external, checks = [], [], []
    rule = lambda op: {'and': [{'field': 'score', 'op': op, 'value': 80},
                              {'field': 'category', 'op': '!=', 'value': 'blocked'}]}
    policy = {'schema': 'executable-clarifications/policy-v1',
              'fields': {'score': 'integer', 'accommodation': 'boolean',
                         'category': {'enum': ['ordinary', 'supervised', 'blocked']}},
              'candidates': [{'id': 'inclusive', 'rule': rule('>=')},
                             {'id': 'exclusive', 'rule': rule('>')}],
              'cases': [{'id': 'boundary', 'input': {
                  'score': 80, 'accommodation': False, 'category': 'ordinary'}}]}
    try:
        with sync_playwright() as pw, tempfile.TemporaryDirectory(dir=scratch):
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_PATH'))
            try:
                context = browser.new_context(accept_downloads=True); page = context.new_page()
                prefix = f'http://127.0.0.1:{server.server_port}/'
                context.route('**/*', lambda r: r.continue_() if r.request.url.startswith(prefix)
                              else (external.append(r.request.url), r.abort()))
                page.on('dialog', lambda dialog: dialog.accept());page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                def record(): return json.loads(page.locator('#record').text_content())
                def upload(data):
                    page.set_input_files('#policy-file', {'name': 'review.json', 'mimeType': 'application/json',
                                                         'buffer': canonical(data).encode()})
                    page.wait_for_function("document.querySelector('#import-status').textContent.startsWith('Imported locally:')")
                def download(selector, name):
                    with page.expect_download() as d: page.click(selector)
                    path = evidence / name; d.value.save_as(path); return path.read_text()
                for width, height in [(1280, 900), (390, 844)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    page.goto(prefix + 'session.html'); upload(policy)
                    assert page.title() == 'Executable Clarifications: adaptive sessions'
                    assert page.locator('h1').inner_text().startswith('Choose behavior.')
                    page.screenshot(path=str(evidence / f'suggestions-entry-{width}.png'), full_page=False)
                    page.click('#answer-true'); original = record()
                    assert PolicySession.from_record(original).status == 'CANDIDATE_SET_NARROWED'
                    button = page.get_by_role('button', name='Suggest boundary and exception cases', exact=True)
                    assert button.is_visible(), 'Missing boundary and exception suggestions action'
                    button.focus(); page.keyboard.press('Enter')
                    page.wait_for_selector('#suggestions-panel:not([hidden])')
                    expected = PolicySession.from_record(original).suggest_cases()
                    assert f"{len(expected['added_cases'])} new, unreviewed" in page.locator('#suggestions-summary').inner_text()
                    summary = page.locator('#suggestions-summary').inner_text()
                    assert '18 of 18 finite-domain combinations represented; 0 omitted.' in summary
                    assert 'Other integers and user intent remain unverified.' in summary
                    assert 'Domains:' in summary
                    limits = page.locator('#suggestions-limits').inner_text()
                    assert 'every multi-field combination of the reported values when all bounds permit.' in limits
                    assert 'limits may leave combinations omitted' in limits
                    assert 'Three-or-more-field combinations are not enumerated' not in summary + limits
                    assert record() == original, 'Preview changed original session'
                    assert page.locator('#suggestions-cases article').count() == len(expected['added_cases'])
                    assert page.locator('#suggestions-title').evaluate('(e)=>e===document.activeElement')
                    page.screenshot(path=str(evidence / f'suggestions-preview-{width}.png'), full_page=False)
                    page.locator('#apply-suggestions').focus(); page.keyboard.press('Enter')
                    page.locator('#revision-panel').wait_for(state='visible')
                    assert page.locator('#revision-panel').is_visible()
                    assert record() == original
                    assert json.loads(download('#download-original', f'original-{width}.json')) == original
                    page.click('#start-revision')
                    page.locator('#start-revision').wait_for(state='hidden')
                    revised = record()
                    assert revised['version_digest'] != original['version_digest']
                    assert PolicySession.from_record(revised).examples() == []
                    assert page.locator('#download-test').is_disabled()
                    reconfirm = page.get_by_role('button', name='Reconfirm boundary as true', exact=True)
                    reconfirm.click(); expect(reconfirm).to_be_disabled()
                    target = {'score': 79, 'accommodation': True, 'category': 'ordinary'}
                    case = next(c for c in expected['added_cases'] if c['input'] == target)
                    row = page.locator(f'#case-review article[data-case-id="{case["id"]}"]')
                    assert 'No operator label' in row.inner_text()
                    assert 'inclusive = false' in row.inner_text()
                    row.get_by_role('button', name='Label true', exact=True).focus(); page.keyboard.press('Enter')
                    assert 'NO_CANDIDATE_MATCH' in page.locator('#status').inner_text()
                    assert page.locator('#outcome-title').inner_text() == 'No rule matches the recorded examples'
                    assert page.locator('#outcome-help').inner_text() == 'Review or revise the candidates. Your recorded examples remain available for export.'
                    labeled = record(); session = PolicySession.from_record(labeled)
                    assert len(session.examples()) == 2
                    contract = download('#download-test', f'contract-{width}.py')
                    assert contract == render_contract(session, 'implementation:decide')
                    saved = download('#download-record', f'session-{width}.json')
                    page.reload(); upload(json.loads(saved)); assert record() == labeled
                    assert download('#download-test', f'resumed-contract-{width}.py') == contract
                    page.click('#undo')
                    assert len(PolicySession.from_record(record()).examples()) == 1
                    page.locator(f'#case-review article[data-case-id="{case["id"]}"]').get_by_role('button', name='Label true', exact=True).click()
                    assert record() == labeled
                    # Bad policy import fails locally and preserves this work.
                    malicious = dict(policy, labels={'boundary': True})
                    page.set_input_files('#policy-file', {'name': 'bad.json', 'mimeType': 'application/json',
                                                         'buffer': canonical(malicious).encode()})
                    page.wait_for_function("document.querySelector('#import-status').textContent.startsWith('Import rejected:')")
                    assert record() == labeled
                    page.locator(f'#case-review article[data-case-id="{case["id"]}"]').evaluate('(e)=>e.scrollIntoView({block:"start"})')
                    page.screenshot(path=str(evidence / f'suggestions-reviewed-{width}.png'), full_page=False)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
                    agree = json.loads(canonical(policy))
                    agree['candidates'][1]['rule'] = agree['candidates'][0]['rule']
                    upload(agree); agreed_record = record()
                    assert page.locator('#question-panel').is_hidden()
                    page.click('#suggest-cases')
                    assert page.locator('#suggestions-panel').is_visible()
                    assert record() == agreed_record
                    assert page.locator('#download-test').is_disabled()
                    page.click('#cancel-suggestions'); assert record() == agreed_record
                    checks.append(f'{width}: keyboard preview/apply, reconfirm, exception label, save/reload/export, private rejection')
                assert not errors, errors
                assert not external, external
                return {'checks': checks, 'console_errors': errors, 'external_requests': external,
                        'browser_plugin': 'not available; pinned Playwright fallback',
                        'scope': 'agent-operated authored fixture; human productivity NOT RUN'}
            finally:
                browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3); lifecycle('closed')


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
