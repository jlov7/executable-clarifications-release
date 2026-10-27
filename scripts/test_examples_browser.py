"""Known-example workflow, over an owned literal-loopback static listener only."""
import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from executable_clarifications.examples import ExampleSet
from executable_clarifications.session import canonical, render_contract


def run():
    root = Path(__file__).resolve().parents[1]
    evidence = Path(os.environ.get('BROWSER_EVIDENCE_DIR', root / '.release-scratch/browser'))
    evidence.mkdir(parents=True, exist_ok=True)
    source = json.loads((root/'tests/fixtures/known_examples.json').read_text())
    policy = json.loads((root/'tests/fixtures/known_examples_candidates.json').read_text())
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(root/'web')))
    def lifecycle(event):
        with (evidence/'servers.jsonl').open('a') as stream:
            stream.write(json.dumps({'event': event, 'pid': os.getpid(), 'host': '127.0.0.1',
                                     'port': server.server_port, 'script': Path(__file__).name})+'\n')
    lifecycle('bound')
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    errors, external, checks = [], [], []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_PATH'))
            try:
                context = browser.new_context(accept_downloads=True); page = context.new_page()
                prefix = f'http://127.0.0.1:{server.server_port}/'
                context.route('**/*', lambda r: r.continue_() if r.request.url.startswith(prefix)
                              else (external.append(r.request.url), r.abort()))
                page.on('dialog', lambda dialog: dialog.accept());page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                def record(): return json.loads(page.locator('#examples-record').text_content())
                def upload(data, selector='#examples-file'):
                    page.set_input_files(selector, {'name': 'review.json', 'mimeType': 'application/json',
                                                   'buffer': canonical(data).encode()})
                def download(selector, name):
                    with page.expect_download() as event: page.click(selector)
                    path = evidence/name; event.value.save_as(path); return path.read_text()
                for width, height in [(1280, 900), (390, 844)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    page.goto(prefix+'session.html')
                    old_policy = page.locator('#record').text_content()
                    page.get_by_role('button', name='Start from known examples', exact=True).click()
                    assert page.locator('#examples-export').is_disabled()
                    # Rerendering typed fields must preserve keyboard navigation and selection.
                    def focused(control): return control.evaluate('(e)=>document.activeElement===e')
                    field = page.locator('#examples-fields > fieldset').first
                    name = field.get_by_label('Name', exact=True)
                    kind = field.get_by_label('Type', exact=True)
                    name.focus(); page.keyboard.press('ControlOrMeta+A'); page.keyboard.type('minutes')
                    page.keyboard.press('Tab')
                    assert focused(kind), 'field rename Tab must advance to the same field Type'
                    for key, value in [('b', 'boolean'), ('e', 'enum'), ('i', 'integer')]:
                        page.keyboard.press(key)
                        assert kind.input_value() == value
                        assert focused(kind), 'keyboard Type selection must retain focus'
                    page.keyboard.press('Shift+Tab'); assert focused(name)
                    page.keyboard.press('ControlOrMeta+A'); page.keyboard.type('duration')
                    page.keyboard.press('Shift+Tab')
                    assert focused(page.locator('#examples-file')), 'rename Shift+Tab must leave fields'
                    page.keyboard.press('Tab'); assert focused(name)
                    page.keyboard.press('ControlOrMeta+A'); page.keyboard.type('minutes')
                    page.keyboard.press('Tab'); assert focused(kind)
                    for add, section, remove, label in [
                            ('#examples-add-field', '#examples-fields', 'Remove field', 'Name'),
                            ('#examples-add-case', '#examples-cases', 'Remove example', 'Example ID')]:
                        for key in ['Enter', 'Space']:
                            page.click(add)
                            row = page.locator(section + ' > fieldset').last
                            row.get_by_role('button', name=remove, exact=True).focus()
                            page.keyboard.press(key)
                            assert page.locator(section + ' > fieldset').count() == 1
                            assert focused(page.locator(section + ' > fieldset').first.get_by_label(label, exact=True)), 'keyboard removal must focus an enabled control'
                    # Author the same five known cases using only typed controls.
                    field = page.locator('#examples-fields > fieldset').first
                    field.get_by_label('Name', exact=True).fill('minutes'); field.get_by_label('Name', exact=True).press('Tab')
                    page.click('#examples-add-field')
                    field = page.locator('#examples-fields > fieldset').nth(1)
                    field.get_by_label('Name', exact=True).fill('emergency'); field.get_by_label('Name', exact=True).press('Tab')
                    page.locator('#examples-fields > fieldset').nth(1).get_by_label('Type', exact=True).select_option('boolean')
                    page.click('#examples-add-field')
                    field = page.locator('#examples-fields > fieldset').nth(2)
                    field.get_by_label('Name', exact=True).fill('channel'); field.get_by_label('Name', exact=True).press('Tab')
                    page.locator('#examples-fields > fieldset').nth(2).get_by_label('Type', exact=True).select_option('enum')
                    enum = page.locator('#examples-fields > fieldset').nth(2).get_by_label('Enum values (comma separated)', exact=True)
                    enum.fill('standard, partner, blocked'); enum.press('Tab')
                    for index, supplied in enumerate(source['examples']):
                        if index: page.click('#examples-add-case')
                        row = page.locator('#examples-cases > fieldset').nth(index)
                        row.get_by_label('Example ID', exact=True).fill(supplied['id']); row.get_by_label('Example ID', exact=True).press('Tab')
                        assert focused(row.get_by_label('minutes', exact=True)), 'example ID Tab must advance exactly once'
                        page.keyboard.press('Shift+Tab'); assert focused(row.get_by_label('Example ID', exact=True))
                        page.keyboard.press('Tab'); assert focused(row.get_by_label('minutes', exact=True))
                        row.get_by_label('minutes', exact=True).fill(str(supplied['input']['minutes'])); row.get_by_label('minutes', exact=True).press('Tab')
                        assert focused(row.get_by_label('emergency', exact=True)), 'input Tab must advance exactly once'
                        row.get_by_label('emergency', exact=True).select_option(str(supplied['input']['emergency']).lower())
                        row.get_by_label('channel', exact=True).select_option(supplied['input']['channel'])
                        row.get_by_label('Expected boolean', exact=True).select_option(str(supplied['expected']).lower())
                    page.click('#examples-review'); page.wait_for_selector('#examples-editor[hidden]', state='attached')
                    assert record()['example_set'] == source
                    assert page.locator('#examples-export').is_disabled()
                    upload(source)
                    page.wait_for_function("document.querySelector('#examples-error').textContent.startsWith('Imported locally.')")
                    assert page.locator('#examples-preview article').count() == 5
                    for row in source['examples']:
                        article = page.locator(f'#examples-preview article[data-example-id="{row["id"]}"]')
                        assert canonical(row['input']) in article.inner_text()
                        assert f'Supplied expected boolean: {str(row["expected"]).lower()}' in article.inner_text()
                    assert page.locator('#examples-export').is_disabled()
                    assert 'PENDING_REVIEW' in page.locator('#examples-status').inner_text()
                    pending = record(); assert not pending['confirmed']
                    page.locator('#examples-review-title').scroll_into_view_if_needed()
                    page.screenshot(path=str(evidence/f'examples-pending-{width}.png'), full_page=False)
                    page.locator('#examples-confirm').focus(); page.keyboard.press('Enter')
                    reviewed = record(); expected = ExampleSet(source); expected.confirm()
                    assert reviewed == expected.export_record()
                    assert 'REVIEWED_EXAMPLES' in page.locator('#examples-status').inner_text()
                    contract = download('#examples-export', f'examples-contract-{width}.py')
                    assert contract == render_contract(expected, 'implementation:decide')
                    assert json.loads(download('#examples-download-set', f'example-set-{width}.json')) == source
                    saved = download('#examples-save', f'example-review-{width}.json')
                    upload(policy, '#examples-audit-file')
                    page.wait_for_function("document.querySelector('#examples-audit').textContent.includes('CANDIDATE_FIT')")
                    audit = json.loads(page.locator('#examples-audit').text_content())
                    assert audit == expected.audit(policy)
                    assert {r['candidate_id']: r['mismatch_ids'] for r in audit['candidates']} == {
                        'intended': [], 'omitted_exception': ['dispatch_exception'], 'exclusive_boundary': ['boundary']}
                    assert record() == reviewed
                    assert download('#examples-export', f'examples-post-audit-{width}.py') == contract
                    page.locator('#examples-audit').scroll_into_view_if_needed()
                    page.screenshot(path=str(evidence/f'examples-audit-{width}.png'), full_page=False)
                    assert page.locator('#record').text_content() == old_policy
                    # Malformed imports preserve record, digest and exports.
                    bad = json.loads(canonical(source)); bad['examples'].append(dict(bad['examples'][0], id='duplicate'))
                    upload(bad)
                    page.wait_for_function("document.querySelector('#examples-error').textContent.startsWith('Import rejected:')")
                    assert record() == reviewed
                    assert download('#examples-original', f'examples-original-{width}.json') == canonical(reviewed)
                    # Valid changed data is pending, and cancel restores the original.
                    changed = json.loads(canonical(source)); changed['examples'][0]['expected'] = False
                    upload(changed)
                    page.wait_for_function("document.querySelector('#examples-error').textContent.startsWith('Imported locally.')")
                    assert record()['version_digest'] != reviewed['version_digest']
                    assert not record()['confirmed']; assert page.locator('#examples-export').is_disabled()
                    page.click('#examples-cancel'); assert record() == reviewed
                    upload(changed)
                    page.wait_for_function("document.querySelector('#examples-error').textContent.startsWith('Imported locally.')")
                    page.click('#examples-confirm')
                    assert record()['confirmed']; assert record()['version_digest'] != reviewed['version_digest']
                    assert json.loads(download('#examples-original', f'examples-before-revision-{width}.json')) == reviewed
                    upload(json.loads(saved))
                    page.wait_for_function("document.querySelector('#examples-error').textContent.startsWith('Imported locally.')")
                    page.click('#examples-confirm'); assert record() == reviewed
                    # Typed editing invalidates confirmation, including expected output edits.
                    page.click('#examples-edit')
                    row = page.locator('#examples-cases > fieldset').first
                    row.get_by_label('minutes', exact=True).fill('16'); row.get_by_label('minutes', exact=True).press('Tab')
                    row.get_by_label('Expected boolean', exact=True).select_option('false')
                    assert page.locator('#examples-export').is_disabled()
                    page.click('#examples-review'); page.wait_for_selector('#examples-editor[hidden]', state='attached')
                    assert record()['example_set']['examples'][0]['input']['minutes'] == 16
                    assert not record()['example_set']['examples'][0]['expected']
                    assert not record()['confirmed']; assert record()['version_digest'] != reviewed['version_digest']
                    page.click('#examples-cancel'); assert record() == reviewed
                    page.reload(); page.click('#start-examples'); upload(json.loads(saved))
                    page.wait_for_function("document.querySelector('#examples-error').textContent.startsWith('Imported locally.')")
                    assert record() == reviewed
                    assert page.locator('#examples-export').is_disabled(), 'Resume preview must be explicitly activated'
                    page.click('#examples-confirm'); assert record() == reviewed
                    assert download('#examples-export', f'examples-resumed-{width}.py') == contract
                    tampered = json.loads(saved); tampered['example_set']['examples'][0]['input']['minutes'] = 16
                    upload(tampered)
                    page.wait_for_function("document.querySelector('#examples-error').textContent.startsWith('Import rejected:')")
                    assert record() == reviewed
                    # A contradictory policy is diagnostic only and cannot change the reviewed truth.
                    none = json.loads(canonical(policy))
                    for candidate in none['candidates']: candidate['rule'] = {'field': 'minutes', 'op': '<', 'value': 0}
                    upload(none, '#examples-audit-file')
                    page.wait_for_function("document.querySelector('#examples-audit').textContent.includes('NO_CANDIDATE_MATCH')")
                    assert record() == reviewed
                    assert download('#examples-export', f'examples-no-match-{width}.py') == contract
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
                    page.locator('#examples-review-title').scroll_into_view_if_needed()
                    page.screenshot(path=str(evidence/f'examples-reviewed-{width}.png'), full_page=False)
                    checks.append(f'{width}: five exact supplied cases, confirm/export/resume, typed edit, malformed/tampered import, cancel, immutable fit/no-match audits')
                assert not errors, errors
                assert not external, external
                return {'checks': checks, 'console_errors': errors, 'external_requests': external,
                        'scope': 'agent-operated authored fixtures; human usability NOT RUN'}
            finally: browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3); lifecycle('closed')


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
