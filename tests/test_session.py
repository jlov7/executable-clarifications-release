import copy
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from executable_clarifications.core import Candidate, ClarificationError


class Sessions(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('executable_clarifications.session'),
                             'Missing adaptive question and implementation contract API')
        from executable_clarifications.session import Session, render_contract
        self.Session, self.render = Session, render_contract
        self.candidates = [Candidate(f'c{i}', 'days', '<=', i) for i in (10, 20, 30, 40)]
        self.session = Session(self.candidates, list(range(42)))

    def test_question_balances_surviving_hypotheses(self):
        q = self.session.question()
        self.assertEqual(sorted(len(v) for v in q['groups'].values()), [2, 2])
        self.assertEqual(q['uniform_expected_remaining'], 2)
        self.assertIn(q['input']['days'], range(21, 31))

    def test_answer_narrows_a_set_not_a_whole_specification(self):
        q = self.session.question()
        self.session.answer(q['id'], True)
        self.assertEqual(self.session.remaining_ids, ('c30', 'c40'))
        self.assertEqual(len(self.session.remaining_ids), 2)
        self.assertEqual(self.session.status, 'OPEN')
        self.assertNotEqual(self.session.question()['id'], q['id'])

    def test_adaptive_session_identifies_all_authored_thresholds(self):
        for intended in self.candidates:
            session = self.Session(self.candidates, list(range(42)))
            questions = 0
            while (q := session.question()) is not None:
                session.answer(q['id'], intended.evaluate(q['input']))
                questions += 1
            self.assertEqual(session.remaining_ids, (intended.id,))
            self.assertEqual(questions, 2)
            self.assertEqual(session.status, 'CANDIDATE_SET_NARROWED')

    def test_no_disagreement_is_not_a_verified_spec(self):
        session = self.Session([Candidate('a','x','<',10),Candidate('b','x','<',20)], [0,1])
        self.assertIsNone(session.question())
        self.assertEqual(session.status, 'NO_FURTHER_DISAGREEMENT')
        with self.assertRaises(ClarificationError): self.render(session, 'implementation:decide')

    def test_neither_preserves_unresolved_and_blocks_export(self):
        self.session.answer(self.session.question()['id'], None)
        self.assertEqual(self.session.status, 'UNRESOLVED')
        self.assertIsNone(self.session.question())
        with self.assertRaises(ClarificationError): self.render(self.session,'implementation:decide')

    def test_question_replay_and_invalid_answers_rejected(self):
        q = self.session.question()
        for answer in [1,0,'true',{},[]]:
            with self.subTest(answer=answer), self.assertRaises(ClarificationError):
                self.session.answer(q['id'], answer)
        self.session.answer(q['id'], True)
        before=self.session.export_record()
        with self.assertRaises(ClarificationError): self.session.answer(q['id'],False)
        self.assertEqual(before,self.session.export_record())

    def test_serialized_history_rederived_and_tampering_refused(self):
        self.session.answer(self.session.question()['id'], False)
        record=self.session.export_record()
        loaded=self.Session.from_record(record)
        self.assertEqual(loaded.export_record(),record)
        broken=copy.deepcopy(record); broken['decisions'][0]['question_id']='0'*64
        with self.assertRaises(ClarificationError): self.Session.from_record(broken)
        broken=copy.deepcopy(record); broken['domain'].append(90)
        with self.assertRaises(ClarificationError): self.Session.from_record(broken)
        broken=copy.deepcopy(record); broken['unexpected']='field'
        with self.assertRaises(ClarificationError): self.Session.from_record(broken)

    def test_constructor_copies_inputs_and_order_does_not_change_questions(self):
        domain=list(range(42)); cs=list(self.candidates)
        session=self.Session(cs,domain)
        cs.clear(); domain.clear()
        self.assertEqual(session.question(), self.session.question())
        other=self.Session(list(reversed(self.candidates)),list(reversed(range(42))))
        self.assertEqual(other.question(),session.question())
        exported=session.export_record(); exported['domain'].clear()
        self.assertIsNotNone(session.question())

    def test_invalid_and_resource_exhausting_domains_refused(self):
        for domain in [[], [True], list(range(1001)), [2**53], ['1']]:
            with self.subTest(domain=str(domain)[:30]), self.assertRaises(ClarificationError):
                self.Session(self.candidates,domain)
        with self.assertRaises(ClarificationError):
            self.Session([self.candidates[0],self.candidates[0]],[1])
        with self.assertRaises(ClarificationError):
            self.Session([self.candidates[0],Candidate('z','other','<',3)],[1])

    def test_bad_targets_never_become_code(self):
        self.session.answer(self.session.question()['id'],True)
        for target in ['os:system()', '__import__("os"):system', 'a:b.c','a/b:c', 'a:class']:
            with self.subTest(target=target), self.assertRaises(ClarificationError):
                self.render(self.session,target)

    def test_export_calls_an_independent_implementation_and_catches_bad_one(self):
        intended=self.candidates[2]
        while (q:=self.session.question()) is not None:
            self.session.answer(q['id'],intended.evaluate(q['input']))
        source=self.render(self.session,'implementation:decide')
        self.assertNotIn('from executable_clarifications',source)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'test_contract.py').write_text(source)
            for body, expected in [('return example["days"] <= 30',0),('return True',1),('return 1',1)]:
                (root/'implementation.py').write_text('def decide(example):\n    '+body+'\n')
                # Disable bytecode to avoid same-second/same-length fixture cache artifacts.
                result=subprocess.run([sys.executable,'-B','test_contract.py'],cwd=root,
                                      capture_output=True,text=True,timeout=10, check=False)
                self.assertEqual(result.returncode,expected,result.stderr)
            (root/'implementation.py').unlink()
            result=subprocess.run([sys.executable,'-B','test_contract.py'],cwd=root,
                                  capture_output=True,text=True,timeout=10, check=False)
            self.assertNotEqual(result.returncode,0)

    def test_export_is_example_scoped_and_partial_status_explicit(self):
        self.session.answer(self.session.question()['id'],True)
        self.assertIn('example-scoped',self.render(self.session,'implementation:decide'))
        self.assertEqual(self.session.export_record()['scope'],'observed-examples-only')
        self.assertEqual(self.session.status,'OPEN')

    def test_malformed_candidate_identity_becomes_a_domain_error(self):
        malformed = Candidate(['not','a','string'], 'days', '<=', 10)
        with self.assertRaises(ClarificationError):
            self.Session([malformed, self.candidates[0]], [1,2])


class SharedBrowserContract(unittest.TestCase):
    def test_python_generated_tree_matches_browser_artifact_digest(self):
        import runpy
        root=Path(__file__).parents[1]
        generator=root/'scripts/build_session_demo.py'
        self.assertTrue(generator.exists(),'Missing shared Python/browser artifact generator')
        rendered=runpy.run_path(str(generator))['render_data']()
        self.assertEqual((root/'web/session-data.js').read_text(), rendered)
        import hashlib
        self.assertEqual((root/'web/session-data.sha256').read_text().strip(),
                         hashlib.sha256(rendered.encode()).hexdigest())

    def test_all_browser_export_leaves_replay_in_python(self):
        import runpy
        root=Path(__file__).parents[1]
        generator=root/'scripts/build_session_demo.py'
        self.assertTrue(generator.exists(),'Missing question tree generator')
        from executable_clarifications.session import Session, render_contract
        payload=runpy.run_path(str(generator))['build_cases']()
        self.assertEqual(len(payload),3)
        total=0
        for case in payload:
            for node in case['nodes'].values():
                session=Session.from_record(node['record'])
                self.assertEqual(session.question(),node['question'])
                if node['contract'] is not None:
                    self.assertEqual(node['contract'],render_contract(session,'implementation:decide'))
                if node['status']=='UNRESOLVED': self.assertIsNone(node['contract'])
                total+=1
        self.assertGreater(total,20)
