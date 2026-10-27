import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from executable_clarifications.core import ClarificationError
from executable_clarifications.policy import PolicySession, load_json
from executable_clarifications.session import canonical, render_contract


def access():
    leaf = lambda op, n: {'field':'score','op':op,'value':n}
    return {'schema':'executable-clarifications/policy-v1',
            'fields':{'score':'integer','trainee':'boolean'},
            'candidates':[{'id':'inclusive','rule':leaf('>=',80)},
                          {'id':'exclusive','rule':leaf('>',80)}],
            'cases':[{'id':'boundary','input':{'score':80,'trainee':False}},
                     {'id':'training','input':{'score':20,'trainee':True}},
                     {'id':'denied','input':{'score':20,'trainee':False}}]}


class ExplicitReview(unittest.TestCase):
    def test_unasked_label_exports_even_without_surviving_candidate(self):
        s=PolicySession(access())
        self.assertEqual(s.case_review()[2]['review_status'], 'unasked')
        self.assertEqual(s.examples(), [])
        s.label_case('training', True)
        self.assertEqual(s.remaining_ids, ())
        self.assertEqual(s.status, 'NO_CANDIDATE_MATCH')
        self.assertEqual(s.examples()[0]['input'], {'score':20,'trainee':True})
        record=s.export_record()
        self.assertEqual(record['schema'], 'executable-clarifications/policy-session-v2')
        self.assertEqual(PolicySession.from_record(load_json(canonical(record))).export_record(),record)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'contract.py').write_text(render_contract(s,'implementation:decide'))
            for rule,code in [('x["score"] >= 80',1),('x["score"] >= 80 or x["trainee"]',0)]:
                (root/'implementation.py').write_text('def decide(x):\n    return '+rule+'\n')
                result=subprocess.run([sys.executable,'-B',str(root/'contract.py')],capture_output=True,timeout=10, check=False)
                self.assertEqual(result.returncode,code)
        s.undo(); self.assertEqual(s.examples(),[])

    def test_answer_then_label_and_label_then_answer_replay(self):
        for first in [True,False]:
            s=PolicySession(access())
            if first: s.answer(s.question()['id'],True)
            s.label_case('denied',False)
            if not first: s.answer(s.question()['id'],True)
            self.assertEqual(PolicySession.from_record(s.export_record()).examples(),s.examples())
            with self.assertRaises(ClarificationError): s.label_case('denied',True)
            record=s.export_record(); record['actions'][0]['extra']=1
            with self.assertRaises(ClarificationError): PolicySession.from_record(record)

    def test_revision_requires_explicit_reconfirmation_and_changed_inputs_fresh(self):
        old=PolicySession(access()); old.answer(old.question()['id'],True); old.label_case('training',True)
        original=old.export_record()
        revised=access(); revised['candidates'][0]['rule']={'or':[revised['candidates'][0]['rule'],{'field':'trainee','op':'==','value':True}]}
        revised['cases'][0]['input']['score']=81
        preview=old.revision_preview(revised)
        self.assertEqual(old.export_record(),original)
        self.assertEqual(preview['changed_rules'],['inclusive'])
        self.assertEqual(preview['changed_cases'],['boundary'])
        self.assertEqual(preview['pending'][0]['review_status'],'fresh-answer-required')
        new=PolicySession(revised)
        self.assertEqual(new.examples(),[])
        with self.assertRaises(ClarificationError): new.reconfirm(old.export_record(),'boundary')
        new.reconfirm(old.export_record(),'training')
        self.assertEqual(new.examples()[0]['expected'],True)
        self.assertEqual(new.export_record()['actions'][0]['source_digest'],old._version)
        self.assertEqual(PolicySession.from_record(new.export_record()).examples(),new.examples())

    def test_v1_exact_bytes_and_questions_unchanged(self):
        s=PolicySession(access()); s.answer(s.question()['id'],True)
        record=s.export_record(); self.assertTrue(record['schema'].endswith('v1'))
        self.assertEqual(canonical(PolicySession.from_record(record).export_record()),canonical(record))


    def test_javascript_review_revision_and_exact_contract_parity(self):
        policy=access(); revised=access()
        revised['candidates'][0]['rule']={'or':[revised['candidates'][0]['rule'],
            {'field':'trainee','op':'==','value':True}]}
        run=subprocess.run(['node',str(Path(__file__).with_name('review-parity.js'))],
            input=json.dumps({'policy':policy,'revised':revised}),text=True,capture_output=True,timeout=10, check=False)
        self.assertEqual(run.returncode,0,run.stderr)
        actual=json.loads(run.stdout); s=PolicySession(policy)
        s.answer(s.question()['id'],True);s.label_case('training',True)
        new=PolicySession(revised);new.reconfirm(s.export_record(),'training')
        self.assertEqual(actual,{'record':s.export_record(),'examples':s.examples(),
            'contract':render_contract(s,'implementation:decide'),
            'preview':s.revision_preview(revised),'revised':new.export_record(),
            'revised_contract':render_contract(new,'implementation:decide')})


    def test_reconfirmed_record_requires_digest_and_unknown_actions_fail_closed(self):
        old=PolicySession(access());old.label_case('training',True)
        revised=access();revised['cases'][0]['input']['score']=81
        new=PolicySession(revised);new.reconfirm(old.export_record(),'training')
        for mutate in [lambda r:r['actions'][0].update(source_digest=None),
                       lambda r:r['actions'][0].update(source_digest='invalid'),
                       lambda r:r['actions'][0].update(kind='automatic'),
                       lambda r:r['actions'][0].update(expected=1),
                       lambda r:r['actions'].append(r['actions'][0])]:
            record=copy.deepcopy(new.export_record());mutate(record)
            with self.assertRaises(ClarificationError):PolicySession.from_record(record)


    def test_v2_max_depth_roundtrip_and_installed_cli_resume(self):
        leaf={'field':'x','op':'>','value':0}; rule=leaf
        for _ in range(6):rule={'or':[rule,leaf]}
        policy={'schema':'executable-clarifications/policy-v1','fields':{'x':'integer'},
                'candidates':[{'id':'a','rule':rule},{'id':'b','rule':leaf}],
                'cases':[{'id':'one','input':{'x':1}}]}
        s=PolicySession(policy);s.label_case('one',True);record=s.export_record()
        self.assertEqual(PolicySession.from_record(load_json(canonical(record))).export_record(),record)
        script="const e=require('./web/policy-engine.js');(async()=>{const s=await e.restore(e.parse(require('node:fs').readFileSync(0,'utf8')));process.stdout.write(e.canonical(s.record()))})().catch(x=>{console.error(x);process.exitCode=1})"
        run=subprocess.run(['node','-e',script],input=canonical(record),text=True,capture_output=True,
                           cwd=Path(__file__).resolve().parents[1],timeout=10, check=False)
        self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(run.stdout,canonical(record))
        with tempfile.TemporaryDirectory() as directory:
            saved=Path(directory)/'review.json';saved.write_text(canonical(record))
            run=subprocess.run([sys.executable,'-I','-m','executable_clarifications.cli',
                                '--resume',str(saved)],capture_output=True,text=True,timeout=10, check=False)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(json.loads(run.stdout)['session'],record)


    def test_boolean_to_integer_revision_requires_fresh_answer_in_both_runtimes(self):
        for boolean, integer in [(True,1),(False,0)]:
            with self.subTest(boolean=boolean):
                policy={'schema':'executable-clarifications/policy-v1','fields':{'x':'boolean'},
                        'candidates':[{'id':'a','rule':{'field':'x','op':'==','value':boolean}},
                                      {'id':'b','rule':{'field':'x','op':'!=','value':boolean}}],
                        'cases':[{'id':'flag','input':{'x':boolean}}]}
                revised=copy.deepcopy(policy);revised['fields']['x']='integer'
                for candidate in revised['candidates']:candidate['rule']['value']=integer
                revised['cases'][0]['input']['x']=integer
                old=PolicySession(policy);old.label_case('flag',True)
                original=canonical(old.export_record())
                run=subprocess.run(['node',str(Path(__file__).with_name('review-parity.js'))],
                    input=json.dumps({'policy':policy,'revised':revised,'type_transition':True}),
                    text=True,capture_output=True,timeout=10, check=False)
                self.assertEqual(run.returncode,0,run.stderr)
                preview=old.revision_preview(revised)
                new=PolicySession(revised)
                self.assertEqual(preview['changed_rules'],['a','b'])
                self.assertEqual(preview['changed_cases'],['flag'])
                self.assertEqual(preview['pending'][0]['review_status'],'fresh-answer-required')
                with self.assertRaises(ClarificationError):new.reconfirm(old.export_record(),'flag')
                self.assertEqual(canonical(old.export_record()),original)
                self.assertEqual(json.loads(run.stdout),{'preview':preview,
                    'original':old.export_record(),'revised':new.export_record()})
