"""Confirmed-example candidate gaps over owned loopback, without target execution."""
import copy
import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from executable_clarifications.conflicts import explain_conflict
from executable_clarifications.examples import ExampleSet
from executable_clarifications.session import canonical, render_contract


def run():
    root = Path(__file__).resolve().parents[1]
    out = Path(os.environ.get('BROWSER_EVIDENCE_DIR', root / '.release-scratch/browser'))
    out.mkdir(parents=True, exist_ok=True)
    source = {'schema': 'executable-clarifications/example-set-v1',
              'fields': {'x': 'integer'}, 'examples': [
                  {'id': name, 'input': {'x': number}, 'expected': False}
                  for name, number in [('one', 1), ('two', 2), ('irrelevant', 3)]]}
    policy = {'schema': 'executable-clarifications/policy-v1', 'fields': source['fields'],
              'candidates': [{'id': 'is_one', 'rule': {'field': 'x', 'op': '==', 'value': 1}},
                             {'id': 'is_two', 'rule': {'field': 'x', 'op': '==', 'value': 2}}],
              'cases': [{'id': 'seed', 'input': {'x': 1}}]}
    reviewed = ExampleSet(source); reviewed.confirm()

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_): pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Quiet, directory=str(root / 'web')))

    def lifecycle(event):
        with (out / 'servers.jsonl').open('a') as stream:
            stream.write(json.dumps({'event': event, 'pid': os.getpid(), 'host': '127.0.0.1',
                                     'port': server.server_port, 'script': Path(__file__).name}) + '\n')

    lifecycle('bound')
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    errors, external, checks = [], [], []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_PATH'))
            try:
                prefix = f'http://127.0.0.1:{server.server_port}/'
                for width, height in [(1280, 900), (390, 844)]:
                    context = browser.new_context(accept_downloads=True,
                                                  viewport={'width': width, 'height': height})
                    page = context.new_page()
                    context.route('**/*', lambda r: r.continue_() if r.request.url.startswith(prefix)
                                  else (external.append(r.request.url), r.abort()))
                    page.on('dialog', lambda dialog: dialog.accept())
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('console', lambda message: errors.append(message.text)
                            if message.type == 'error' else None)

                    def upload(data, selector='#examples-file', page=page):
                        page.set_input_files(selector, {'name': 'local.json',
                            'mimeType': 'application/json', 'buffer': canonical(data).encode()})

                    def download(selector, name, page=page, width=width):
                        with page.expect_download() as event:
                            page.click(selector)
                        path = out / f'conflicts-{width}-{name}'
                        event.value.save_as(path)
                        return path.read_text()

                    def explain(candidates, page=page, upload=upload):
                        upload(candidates, '#examples-audit-file')
                        expect(page.locator('#examples-audit-review')).to_be_visible()
                        expect(page.locator('#examples-explain')).to_be_disabled()
                        expect(page.locator('#examples-explanation')).to_be_hidden()
                        page.focus('#examples-audit-confirm'); page.keyboard.press('Space')
                        page.keyboard.press('Tab')
                        assert page.locator('#examples-explain').evaluate('(n)=>n===document.activeElement')
                        page.keyboard.press('Enter')
                        expect(page.locator('#examples-explanation')).to_be_visible()
                        assert page.locator('#examples-explanation-title').evaluate('(n)=>n===document.activeElement')
                        result = json.loads(page.locator('#examples-explanation-json').text_content())
                        assert result == explain_conflict(reviewed, candidates)
                        return result

                    try:
                        page.goto(prefix + 'session.html')
                        page.click('#answer-true')
                        policy_record = page.locator('#record').text_content()
                        page.click('#start-examples'); upload(source)
                        expect(page.locator('#examples-confirm')).to_be_enabled()
                        expect(page.locator('#examples-audit-file')).to_be_disabled()
                        expect(page.locator('#examples-explanation')).to_be_hidden()
                        page.click('#examples-confirm')
                        record = page.locator('#examples-record').text_content()
                        assert json.loads(record) == reviewed.export_record()
                        contract = download('#examples-export', 'contract.py')
                        assert contract == render_contract(reviewed, 'implementation:decide')
                        report = explain(policy)
                        assert report['core_example_ids'] == ['one', 'two']
                        body = page.locator('#examples-explanation-body').inner_text()
                        for text in ('deletion-minimal', 'globally smallest', 'Confirmed example one',
                                     'Confirmed example two', 'is_one predicts true for one',
                                     'Omit one: is_one', 'Omit two: is_two', 'does not judge labels incorrect'):
                            assert text in body, text
                        assert json.loads(download('#examples-explanation-save', 'explanation.json')) == report
                        expect(page.locator('#save-status')).to_contain_text('Unsaved')
                        assert page.locator('#examples-record').text_content() == record
                        assert page.locator('#record').text_content() == policy_record
                        assert download('#examples-export', 'post-explanation.py') == contract
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                        page.locator('#examples-explanation').screenshot(path=str(out / f'conflicts-gap-{width}.png'))
                        # Revoking candidate review hides the computed result immediately.
                        page.uncheck('#examples-audit-confirm')
                        expect(page.locator('#examples-explanation')).to_be_hidden()
                        expect(page.locator('#examples-explain')).to_be_disabled()
                        # A separately reviewed consistent candidate is an alternative, not a conflict.
                        consistent = copy.deepcopy(policy)
                        consistent['candidates'].append({'id': 'always_false',
                            'rule': {'field': 'x', 'op': '<', 'value': 0}})
                        fit = explain(consistent)
                        assert fit['fitting_candidates'] == ['always_false']
                        assert fit['core_example_ids'] == []
                        expect(page.locator('#examples-explanation-body')).to_contain_text('No conflict subset is needed')
                        page.locator('#examples-explanation').screenshot(path=str(out / f'conflicts-fit-{width}.png'))
                        # Even a rejected candidate replacement clears the old audit and explanation.
                        upload({'schema': 'invalid'}, '#examples-audit-file')
                        expect(page.locator('#examples-error')).to_contain_text('Audit rejected:')
                        expect(page.locator('#examples-explanation')).to_be_hidden()
                        expect(page.locator('#examples-audit-review')).to_be_hidden()
                        explain(policy)
                        page.click('#examples-edit')
                        page.locator('#examples-cases > fieldset').first.get_by_label('Expected boolean', exact=True).select_option('true')
                        expect(page.locator('#examples-explanation')).to_be_hidden()
                        expect(page.locator('#examples-audit-review')).to_be_hidden()
                        expect(page.locator('#examples-export')).to_be_disabled()
                        page.click('#examples-review')
                        expect(page.locator('#examples-confirm')).to_be_enabled()
                        expect(page.locator('#examples-explanation')).to_be_hidden()
                        page.click('#examples-cancel')
                        assert page.locator('#examples-record').text_content() == record
                        expect(page.locator('#examples-explain')).to_be_disabled()
                        explain(policy)
                        saved = download('#examples-save', 'review.json')
                        assert json.loads(saved) == reviewed.export_record()
                        expect(page.locator('#save-status')).to_contain_text('Unsaved')
                        download('#download-record', 'policy.json')
                        expect(page.locator('#save-status')).not_to_contain_text('Unsaved')
                        page.reload(); page.click('#start-examples'); upload(json.loads(saved))
                        expect(page.locator('#examples-confirm')).to_be_enabled()
                        expect(page.locator('#examples-audit-file')).to_be_disabled()
                        expect(page.locator('#examples-explanation')).to_be_hidden()
                        page.click('#examples-confirm')
                        assert page.locator('#examples-record').text_content() == record
                        assert download('#examples-export', 'restored.py') == contract
                        explain(policy)
                        changed = copy.deepcopy(source); changed['examples'][0]['expected'] = True
                        upload(changed)
                        expect(page.locator('#examples-confirm')).to_be_enabled()
                        expect(page.locator('#examples-explanation')).to_be_hidden()
                        expect(page.locator('#examples-audit-review')).to_be_hidden()
                        expect(page.locator('#examples-audit-file')).to_be_disabled()
                        page.click('#examples-cancel')
                        assert page.locator('#examples-record').text_content() == record
                        checks.append(f'{width}: confirmed gap and all witnesses match Python; consistent '
                            'alternative; keyboard report focus; edit/import/revoked-review invalidation; '
                            'unchanged review/contract; save/restore and independent unsaved warnings')
                    except BaseException:
                        page.screenshot(path=str(out / f'conflicts-failure-{width}.png'), full_page=True)
                        raise
                    finally:
                        context.close()
            finally:
                browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3); lifecycle('closed')
    assert not errors and not external, (errors, external)
    return {'checks': checks, 'console_errors': errors, 'external_requests': external,
            'scope': 'agent-operated authored fixtures; human usefulness and screen-reader study NOT RUN'}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
