"""Owned local desktop/mobile review journeys; no provider or human evidence."""
import json
import os
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from executable_clarifications.policy import PolicySession
from executable_clarifications.session import render_contract


def run():
    root=Path(__file__).resolve().parents[1]
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*_): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(root/'web')))
    def lifecycle(event):
        if os.environ.get('BROWSER_EVIDENCE_DIR'):
            out=Path(os.environ['BROWSER_EVIDENCE_DIR']);out.mkdir(parents=True,exist_ok=True)
            with (out/'servers.jsonl').open('a') as stream:
                stream.write(json.dumps({'event':event,'pid':os.getpid(),'host':'127.0.0.1',
                                        'port':server.server_port,'script':Path(__file__).name})+'\n')
    lifecycle('bound')
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[];external=[];checks=[]
    try:
        with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmp:
            browser=pw.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH'))
            context=browser.new_context(accept_downloads=True);page=context.new_page()
            prefix=f'http://127.0.0.1:{server.server_port}/'
            context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(prefix) else (external.append(r.request.url),r.abort()))
            page.on('dialog', lambda dialog: dialog.accept());page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
            def record():return json.loads(page.locator('#record').text_content())
            def screenshot(name, full_page=True):
                out=os.environ.get('BROWSER_EVIDENCE_DIR')
                if out:
                    Path(out).mkdir(parents=True,exist_ok=True);page.screenshot(path=str(Path(out)/name),full_page=full_page)
            def download(selector,name):
                with page.expect_download() as d:page.click(selector)
                path=Path(tmp)/name;d.value.save_as(path);return path.read_text()
            def predicate(box,field,op,value):
                box.get_by_label('Field',exact=True).select_option(field)
                box.get_by_label('Operator',exact=True).select_option(op)
                control=box.get_by_label('Value',exact=True)
                if control.evaluate('(e)=>e.tagName')=='SELECT':control.select_option(str(value).lower() if isinstance(value,bool) else str(value))
                else:control.fill(str(value));control.press('Tab')
            def focused(control):return control.evaluate('(node)=>node===document.activeElement')
            for width,height in [(1280,900),(390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                for imported in [False,True]:
                    for collection,add,label,remove in [('candidates','add-candidate','Candidate ID','Remove candidate'),('cases','add-case','Case ID','Remove case')]:
                        for deleted in [0,1]:
                            page.goto(prefix+'session.html')
                            if imported:
                                spec={'schema':'executable-clarifications/policy-v1','fields':{'x':'integer'},
                                      'candidates':[{'id':identity,'rule':{'field':'x','op':'>=','value':i}} for i,identity in enumerate(['candidate1','candidate3','candidate4','custom'])],
                                      'cases':[{'id':identity,'input':{'x':i}} for i,identity in enumerate(['case1','case3','case4','custom'])]}
                                page.set_input_files('#policy-file',{'name':'sparse.json','mimeType':'application/json','buffer':json.dumps(spec).encode()})
                                expect(page.locator('#import-status')).to_contain_text('Imported locally:')
                            page.click('#open-editor')
                            if not imported:
                                for _ in range(2 if collection=='candidates' else 3):page.click('#'+add)
                            before=json.loads(page.locator('#editor-preview').text_content())[collection]
                            row=page.locator('#editor-'+collection+' > fieldset').nth(deleted)
                            deleted_id=row.get_by_label(label,exact=True).input_value()
                            row.get_by_role('button',name=remove,exact=True).click()
                            page.click('#'+add)
                            after=json.loads(page.locator('#editor-preview').text_content())[collection]
                            assert len({c['id'] for c in after})==len(after),(width,collection,imported,deleted,after)
                            assert all(c in after for c in before if c['id']!=deleted_id)
                            exported=json.loads(download('#download-policy',f'identities-{width}.json'))
                            assert exported==PolicySession(exported)._policy
                            page.click('#apply-policy');expect(page.locator('#all-cases-panel')).to_be_visible()
                            if imported:
                                expect(page.locator('#start-revision')).to_be_visible()
                                assert record()['policy']==PolicySession(spec)._policy
                                page.click('#start-revision')
                            page.wait_for_function("policy=>window.PolicyEngine.canonical(JSON.parse(document.querySelector('#record').textContent).policy)===window.PolicyEngine.canonical(policy)",arg=exported)
                            assert record()['policy']==exported
                # Count only the revised session's review, keeping the original revision preview independent.
                spec={'schema':'executable-clarifications/policy-v1','fields':{'x':'integer'},
                      'candidates':[{'id':name,'rule':{'field':'x','op':op,'value':0}} for name,op in [('a','>='),('b','>')]],
                      'cases':[{'id':f'c{i:02d}','input':{'x':i+1}} for i in range(16)]}
                session=PolicySession(spec)
                for case in spec['cases']:session.label_case(case['id'],True)
                original=session.export_record()
                page.goto(prefix+'session.html')
                page.set_input_files('#policy-file',{'name':'reviewed.json','mimeType':'application/json','buffer':json.dumps(original).encode()})
                expect(page.locator('#import-status')).to_contain_text('Imported locally:')
                page.evaluate("""() => {const create=window.PolicyEngine.create;window.reviewCalls=0;window.countReviews=false;window.PolicyEngine.create=async policy=>{const s=await create(policy),review=s.caseReview.bind(s);s.caseReview=(...args)=>{if(window.countReviews)window.reviewCalls++;return review(...args)};return s;};}""")
                page.click('#open-editor')
                value=page.locator('#editor-candidates > fieldset').first.get_by_label('Value',exact=True)
                value.fill('-1');value.press('Tab');page.click('#apply-policy')
                expect(page.locator('#start-revision')).to_be_visible();assert record()==original
                page.evaluate('() => {window.reviewCalls=0;window.countReviews=true;}')
                page.click('#start-revision')
                buttons=page.locator('#pending-review button');expect(buttons).to_have_count(16)
                assert page.evaluate('window.reviewCalls')==1,page.evaluate('window.reviewCalls')
                revised=record();assert revised['decisions']==[]
                assert page.locator('#case-review article').count()==16
                assert buttons.evaluate_all('(nodes)=>nodes.every(n=>!n.disabled)')
                for case in spec['cases']:assert case['id'] in page.locator('#pending-review').inner_text()
                page.evaluate('window.reviewCalls=0');buttons.first.click();expect(buttons.first).to_be_disabled()
                assert page.evaluate('window.reviewCalls')==1
                restored=PolicySession.from_record(record())
                assert len(restored.examples())==1 and restored.export_record()['actions'][0]['kind']=='reconfirmed'
                assert restored.export_record()['version_digest']==revised['version_digest']
                assert buttons.evaluate_all('(nodes)=>nodes.filter(n=>n.disabled).length')==1
                assert download('#download-test',f'counted-contract-{width}.py')==render_contract(restored,'implementation:decide')
                checks.append(f'{width}: delete/add earlier and middle rows / sparse imported IDs / unchanged survivors / valid policy download and activation / 16-row fresh review calls=1 / reconfirm render calls=1 / exact contract')
                # Reviewed examples miss both a boundary edit and a membership exception.
                impact_policy={'schema':'executable-clarifications/policy-v1',
                    'fields':{'minutes':'integer','member':'boolean','blocked':'boolean'},
                    'candidates':[{'id':'access','rule':{'field':'minutes','op':'<=','value':30}},
                                  {'id':'other','rule':{'field':'minutes','op':'<','value':10}}],
                    'cases':[{'id':'early','input':{'minutes':5,'member':False,'blocked':False}},
                             {'id':'late','input':{'minutes':60,'member':False,'blocked':False}}]}
                impact_session=PolicySession(impact_policy)
                impact_session.label_case('early',True);impact_session.label_case('late',False)
                impact_original=impact_session.export_record()
                page.goto(prefix+'session.html')
                page.set_input_files('#policy-file',{'name':'impact-session.json','mimeType':'application/json','buffer':json.dumps(impact_original).encode()})
                expect(page.locator('#import-status')).to_contain_text('Imported locally:')
                page.click('#open-editor')
                page.locator('#editor-candidates > fieldset').first.get_by_label('Condition type',exact=True).select_option('or')
                nested=page.locator('#editor-candidates > fieldset').first.locator('fieldset > fieldset')
                predicate(nested.nth(0),'minutes','<',30);predicate(nested.nth(1),'member','==',True)
                proposed=json.loads(page.locator('#editor-preview').text_content())
                expected_impact=impact_session.compare_policy(proposed)
                assert [(c['false_to_true_count'],c['true_to_false_count']) for c in expected_impact['candidate_impacts']]==[(8,2),(0,0)]
                page.click('#apply-policy');expect(page.locator('#impact-summary')).to_contain_text('48 of 48')
                assert json.loads(page.locator('#impact-json').text_content())==expected_impact
                expect(page.locator('#impact-candidates')).to_contain_text('0 distinct recorded inputs')
                expect(page.locator('#impact-witnesses')).to_contain_text('Missed by recorded examples')
                assert page.locator('#impact-witnesses article').count()==2
                assert record()==impact_original
                assert json.loads(download('#download-original',f'impact-original-{width}.json'))==impact_original
                page.get_by_text('Coverage, limits and exact comparison report',exact=True).click()
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                screenshot(f'policy-impact-before-start-{width}.png')
                page.click('#start-revision');expect(page.locator('#start-revision')).to_be_hidden()
                assert PolicySession.from_record(record()).examples()==[]
                assert json.loads(page.locator('#impact-json').text_content())==expected_impact
                assert json.loads(download('#download-original',f'impact-after-start-{width}.json'))==impact_original
                checks.append(f'{width}: unseen exception and boundary impact / exact Python parity / unchanged finite candidate / unlabelled witnesses before start / original download / empty revised session / no overflow')
                page.set_input_files('#policy-file',{'name':'impact-original.json','mimeType':'application/json','buffer':json.dumps(impact_original).encode()})
                expect(page.locator('#import-status')).to_contain_text('Imported locally:')
                page.click('#open-editor');page.click('#add-field')
                name=page.locator('#editor-fields > fieldset').last.get_by_label('Name',exact=True)
                name.fill('toString');name.press('Tab')
                page.locator('#editor-fields > fieldset').last.get_by_label('Type',exact=True).select_option('boolean')
                incompatible=json.loads(page.locator('#editor-preview').text_content())
                page.click('#apply-policy');expect(page.locator('#impact-summary')).to_contain_text('Incompatible field vocabulary')
                assert json.loads(page.locator('#impact-json').text_content())==impact_session.compare_policy(incompatible)
                assert record()==impact_original
                assert json.loads(download('#download-original',f'incompatible-original-{width}.json'))==impact_original
                page.click('#start-revision');expect(page.locator('#start-revision')).to_be_hidden()
                assert PolicySession.from_record(record()).examples()==[]
                checks.append(f'{width}: valid builtin-name field addition / explicit incompatible vocabulary / exact Python parity / original preserved / empty revision')
            for width,height in [(1280,900),(390,844)]:
                page.set_viewport_size({'width':width,'height':height});page.goto(prefix+'session.html')
                assert page.title()=='Executable Clarifications: adaptive sessions'
                page.click('#open-editor');assert page.locator('#policy-editor').is_visible()
                keyboard_problems=[]
                first_name=page.locator('#editor-fields > fieldset').first.get_by_label('Name',exact=True)
                first_name.focus();page.keyboard.press('ControlOrMeta+A');page.keyboard.type('rating',delay=75)
                page.keyboard.press('Shift+Tab',delay=100)
                if not focused(page.locator('#scenario')):keyboard_problems.append('first-field rename Shift+Tab must leave the editor')
                page.locator('#scenario').focus();page.keyboard.press('Tab',delay=100);assert focused(first_name)
                page.keyboard.press('ControlOrMeta+A');page.keyboard.type('score',delay=75);page.keyboard.press('Tab',delay=100)
                if not focused(page.locator('#editor-fields > fieldset').first.get_by_label('Type',exact=True)):keyboard_problems.append('first-field rename Tab must advance once')
                first_name.focus();page.keyboard.press('Shift+Tab',delay=100);assert focused(page.locator('#scenario'))
                page.click('#open-editor')
                if not focused(page.locator('#open-editor')):keyboard_problems.append('leaving the editor must clear pending keyboard navigation')
                page.click('#add-field')
                field=page.locator('#editor-fields > fieldset').nth(1)
                name=field.get_by_label('Name',exact=True);kind=field.get_by_label('Type',exact=True)
                name.focus();page.keyboard.press('ControlOrMeta+A');page.keyboard.type('trainee',delay=75)
                page.keyboard.press('Tab',delay=100)
                if not focused(kind):keyboard_problems.append('rename Tab must advance to the same field Type')
                for key,value in [('b','boolean'),('e','enum'),('b','boolean')]:
                    if not focused(kind):kind.focus()
                    page.keyboard.press(key,delay=100)
                    assert kind.input_value()==value
                    if not focused(kind):keyboard_problems.append('type keyboard selection must retain the same field Type')
                kind.focus();page.keyboard.press('Shift+Tab',delay=100)
                assert focused(name) and name.input_value()=='trainee'
                page.keyboard.press('Tab',delay=100);assert focused(kind)
                first_rule=page.locator('#editor-candidates > fieldset').first
                for label,keys in [('Field',[('t','trainee'),('s','score')]),('Operator',[('!','!='),('<','<')])]:
                    control=first_rule.get_by_label(label,exact=True)
                    control.focus()
                    for key,value in keys:
                        page.keyboard.press(key,delay=100)
                        assert control.input_value()==value
                        if not focused(control):keyboard_problems.append(label+' keyboard selection must retain its control');control.focus()
                page.click('#add-candidate')
                page.locator('#editor-candidates > fieldset').last.get_by_role('button',name='Remove candidate',exact=True).focus()
                page.keyboard.press('Enter',delay=100)
                assert page.locator('#editor-candidates > fieldset').count()==2
                if not focused(page.locator('#editor-candidates > fieldset').last.get_by_label('Candidate ID',exact=True)):keyboard_problems.append('removing a candidate must focus an enabled control')
                page.click('#add-case')
                page.locator('#editor-cases > fieldset').last.get_by_role('button',name='Remove case',exact=True).focus()
                page.keyboard.press('Enter',delay=100)
                assert page.locator('#editor-cases > fieldset').count()==1
                if not focused(page.locator('#editor-cases > fieldset').first.get_by_label('Case ID',exact=True)):keyboard_problems.append('removing a case must focus an enabled control')
                for section,add,label in [('editor-candidates','add-candidate','Candidate ID'),('editor-cases','add-case','Case ID')]:
                    page.click('#'+add)
                    page.locator('#'+section+' > fieldset').last.get_by_role('button',name='Remove candidate' if label=='Candidate ID' else 'Remove case',exact=True).focus()
                    page.keyboard.press('Space',delay=100)
                    if not focused(page.locator('#'+section+' > fieldset').last.get_by_label(label,exact=True)):keyboard_problems.append('Space removal must focus an enabled '+label)
                assert not keyboard_problems,keyboard_problems
                for i,op in enumerate(['>=','>']):predicate(page.locator('#editor-candidates > fieldset').nth(i),'score',op,80)
                for name,trainee in [('denied',False),('training',True)]:
                    page.click('#add-case');box=page.locator('#editor-cases > fieldset').last
                    box.get_by_label('Case ID',exact=True).fill(name);box.get_by_label('Case ID',exact=True).press('Tab')
                    box.get_by_label('score',exact=True).fill('20');box.get_by_label('score',exact=True).press('Tab')
                    box.get_by_label('trainee',exact=True).select_option(str(trainee).lower())
                policy=json.loads(page.locator('#editor-preview').text_content())
                assert PolicySession(policy).question()['case_id']=='boundary'
                exported_policy=json.loads(download('#download-policy',f'policy-{width}.json'));assert exported_policy==PolicySession(policy)._policy
                screenshot(f'add21-typed-editor-{width}.png')
                page.click('#apply-policy');page.locator('#all-cases-panel').wait_for(state='visible')
                assert page.locator('#all-cases-panel').is_visible()
                training=page.locator('#case-review article[data-case-id="training"]')
                assert 'unasked' in training.inner_text();assert 'inclusive = false' in training.inner_text();assert 'No operator label' in training.inner_text()
                assert page.locator('#download-test').is_disabled()
                # Keyboard reads full exact rule; differences are already visible without expansion.
                assert any('>=' in text for text in page.locator('#interpretations mark').all_text_contents())
                assert any(' > ' in text for text in page.locator('#interpretations mark').all_text_contents())
                summary=page.locator('#interpretations summary').first;summary.focus();page.keyboard.press('Enter')
                assert summary.locator('..').get_attribute('open') is not None
                page.click('#answer-true')
                original_before=record();assert original_before['schema'].endswith('v1')
                page.click('#open-editor');page.click('#apply-policy')
                assert record()==original_before, 'Unchanged editor apply discarded adaptive answers'
                training.get_by_role('button',name='Label true',exact=True).click()
                original=record();assert original['schema'].endswith('v2');assert 'NO_CANDIDATE_MATCH' in page.locator('#status').inner_text()
                session=PolicySession.from_record(original);assert len(session.examples())==2
                contract=download('#download-test',f'contract-{width}.py');assert contract==render_contract(session,'implementation:decide')
                saved=download('#download-record',f'session-{width}.json');assert json.loads(saved)==original
                screenshot(f'add21-unasked-label-{width}.png')
                page.reload();page.set_input_files('#policy-file',{'name':'session.json','mimeType':'application/json','buffer':saved.encode()});page.wait_for_function("document.querySelector('#import-status').textContent.startsWith('Imported locally:')")
                assert record()==original
                page.click('#open-editor');page.click('#apply-policy')
                assert record()==original, 'Unchanged editor apply discarded explicit labels'
                # Add missing trainee exception entirely through grouped typed controls.
                page.click('#open-editor')
                first=page.locator('#editor-candidates > fieldset').first
                first.get_by_label('Condition type',exact=True).select_option('or')
                nested=page.locator('#editor-candidates > fieldset').first.locator('fieldset > fieldset')
                predicate(nested.nth(0),'score','>=',80);predicate(nested.nth(1),'trainee','==',True)
                # Changed boundary case must get a fresh answer, never a reconfirm button.
                page.locator('#editor-cases > fieldset').first.get_by_label('score',exact=True).fill('81')
                page.locator('#editor-cases > fieldset').first.get_by_label('score',exact=True).press('Tab')
                page.click('#apply-policy');assert record()==original
                expect(page.locator('#revision-summary')).to_contain_text('exclusive')
                assert 'fresh-answer-required' in page.locator('#pending-review').inner_text()
                assert json.loads(download('#download-original',f'original-{width}.json'))==original
                page.click('#start-revision')
                reconfirm=page.get_by_role('button',name='Reconfirm training as true',exact=True)
                expect(reconfirm).to_be_visible()
                assert PolicySession.from_record(record()).examples()==[]
                assert page.get_by_role('button',name='Reconfirm boundary as true',exact=True).count()==0
                reconfirm.click();expect(reconfirm).to_be_disabled()
                revised=PolicySession.from_record(record());assert len(revised.examples())==1
                assert revised.export_record()['actions'][0]['kind']=='reconfirmed'
                assert download('#download-test',f'revised-{width}.py')==render_contract(revised,'implementation:decide')
                page.locator('#case-review article[data-case-id="boundary"]').get_by_role('button',name='Label true',exact=True).click()
                assert len(PolicySession.from_record(record()).examples())==2
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                screenshot(f'add21-reconfirmed-{width}.png')
                checks.append(f'{width}: typed access build without JSON / policy export / explicit unasked trainee label / exact contract / v2 save-resume / grouped OR revision / original preserved / changed input fresh / explicit reconfirm')
            # New support policy task with categorical membership and structurally shared AND.
            support={'schema':'executable-clarifications/policy-v1','fields':{'minutes':'integer','tier':{'enum':['standard','priority']}},'candidates':[],'cases':[{'id':'edge','input':{'minutes':30,'tier':'priority'}},{'id':'ordinary','input':{'minutes':20,'tier':'standard'}}]}
            for name,op in [('inclusive','<='),('exclusive','<')]:support['candidates'].append({'id':name,'rule':{'and':[{'field':'tier','op':'in','value':['priority']},{'field':'minutes','op':op,'value':30}]}})
            page.set_input_files('#policy-file',{'name':'support.json','mimeType':'application/json','buffer':json.dumps(support).encode()});page.wait_for_function("document.querySelector('#import-status').textContent.includes('support.json')")
            assert page.locator('#shared-conditions').inner_text().count('tier in')==1
            assert page.locator('#interpretations mark').first.inner_text()=='minutes < 30'
            assert all('shared clause' not in text for text in page.locator('#interpretations mark').all_text_contents())
            assert page.locator('#interpretations details[open]').count()==0
            problems=[]
            help_text=page.locator('#question-help').inner_text()
            if 'Build or edit a policy with forms' not in help_text or 'Review this policy' not in help_text:
                problems.append('question help must name the typed editor and revision actions')
            rule_cell=page.locator('#interpretations tr').first.locator('td').nth(1)
            if rule_cell.bounding_box()['width'] < 250:
                problems.append('mobile rule must use a readable full-width row')
            if rule_cell.locator('summary').bounding_box()['height'] > 30:
                problems.append('mobile full-rule disclosure must fit on one line')
            assert page.get_by_role('table',name='Candidate behavior on this input').count()==1
            assert page.locator('#interpretations').get_by_role('cell').count()==6
            assert not problems,problems
            page.locator('#question-panel').scroll_into_view_if_needed();screenshot('add21-support-differences-before-expansion-390.png',False)
            page.click('#open-editor');assert page.locator('#editor-fields').get_by_label('Enum values (comma separated)',exact=True).input_value()=='standard, priority'
            assert page.locator('#editor-candidates').get_by_label('Member 1',exact=True).count()==2
            enum_values=page.locator('#editor-fields').get_by_label('Enum values (comma separated)',exact=True)
            enum_values.fill('standard, priority, urgent');enum_values.press('Tab')
            assert page.locator('#editor-candidates select[aria-label="Member 1"] option[value="urgent"]').count()==2
            enum_values.fill('standard, priority');enum_values.press('Tab')
            # Rebuild an exact grouped AND rule with typed categorical membership.
            first=page.locator('#editor-candidates > fieldset').first
            first.get_by_label('Condition type',exact=True).first.select_option('or')
            first.get_by_label('Condition type',exact=True).first.select_option('and')
            nested=page.locator('#editor-candidates > fieldset').first.locator('fieldset > fieldset')
            predicate(nested.nth(0),'tier','==','priority')
            nested.nth(0).get_by_label('Operator',exact=True).select_option('in')
            nested.nth(0).get_by_label('Member 1',exact=True).select_option('priority')
            predicate(nested.nth(1),'minutes','<',30)
            assert json.loads(page.locator('#editor-preview').text_content())==PolicySession(support)._policy
            page.click('#apply-policy');page.click('#answer-true')
            assert PolicySession.from_record(record()).remaining_ids==('inclusive',)
            screenshot('add21-support-differences-390.png')
            checks.append('new support task: categorical membership form / shared clause once / differing boundary before full-rule expansion / unchanged exact policy contract')
            assert not errors,errors
            assert not external,external
            context.close();browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3);lifecycle('closed')
    return {'checks':checks,'console_errors':errors,'external_requests':external,'claim_ceiling':'Agent-operated authored local tasks. Human completion and intent validation NOT RUN.'}

if __name__=='__main__':print(json.dumps(run(),indent=2))
