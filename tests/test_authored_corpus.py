import ast
import importlib.util
import json
import runpy
import unittest
from pathlib import Path

from executable_clarifications.core import ClarificationError
from executable_clarifications.session import Session, render_contract


class AuthoredCorpus(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('executable_clarifications.generation'),
                             'Missing reviewed JSON integer-predicate generator')
        from executable_clarifications.generation import generate_candidates
        self.generate = generate_candidates
        self.root = Path(__file__).parents[1]
        fixtures = self.root / 'tests/fixtures'
        self.inputs = json.loads((fixtures / 'reviewed_candidates.json').read_text())['cases']
        self.labels = json.loads((fixtures / 'intended_behavior.json').read_text())['cases']

    def answered_session(self, case_id):
        case = self.inputs[case_id]
        candidates = self.generate(case['generator_input'])
        session = Session(candidates, case['domain'])
        for _ in range(64):
            q = session.question()
            if q is None:
                return session, candidates
            label = next(row for row in self.labels[case_id] if row['input'] == q['input'])
            session.answer(q['id'], label['expected'])
        self.fail('Bounded authored session did not terminate')

    def test_authored_labels_drive_exported_observed_examples(self):
        session, candidates = self.answered_session('age_window')
        self.assertEqual(session.status, 'CANDIDATE_SET_NARROWED')
        self.assertEqual(session.remaining_ids, ('c3',))
        self.assertEqual([(row['input'], row['expected']) for row in session.examples()],
                         [({'days': 21}, True), ({'days': 30}, True)])
        source = render_contract(session, 'implementation:decide')
        # Inspect the literal JSON payload without executing exported code or importing a target.
        assignment = next(node for node in ast.parse(source).body
                          if isinstance(node, ast.Assign))
        data = json.loads(ast.literal_eval(assignment.value.args[0]))
        self.assertEqual(data['examples'], session.examples())
        chosen = next(c for c in candidates if c.id == session.remaining_ids[0])
        self.assertTrue(all(chosen.evaluate(row['input']) is row['expected']
                            for row in self.labels['age_window']))

    def test_agreeing_control_asks_nothing_and_cannot_export_assertions(self):
        session, _ = self.answered_session('constant_control')
        self.assertEqual(session.status, 'NO_FURTHER_DISAGREEMENT')
        self.assertEqual(session.examples(), [])
        with self.assertRaises(ClarificationError):
            render_contract(session, 'implementation:decide')

    def test_narrowing_can_miss_authored_behavior_outside_observed_examples(self):
        session, candidates = self.answered_session('candidate_miss')
        self.assertEqual(session.status, 'CANDIDATE_SET_NARROWED')
        chosen = next(c for c in candidates if c.id == session.remaining_ids[0])
        mismatches = [row for row in self.labels['candidate_miss']
                      if chosen.evaluate(row['input']) is not row['expected']]
        self.assertEqual(mismatches, [{'input': {'days': 29}, 'expected': False}])
        self.assertEqual([row['input'] for row in session.examples()], [{'days': 30}])

    def test_label_tables_are_not_accepted_as_generator_inputs(self):
        with self.assertRaises(ClarificationError):
            self.generate(dict(self.inputs['age_window']['generator_input'],
                               intended_labels=self.labels['age_window']))

    def test_runnable_authored_example_connects_generation_session_and_export(self):
        script = self.root / 'scripts/run_authored_example.py'
        self.assertTrue(script.exists(), 'Missing runnable authored generator example')
        result = runpy.run_path(str(script))['run']()
        self.assertEqual(result['provenance'], 'authored regression fixtures, not human evidence')
        self.assertEqual(result['session']['scope'], 'observed-examples-only')
        restored = Session.from_record(result['session'])
        self.assertEqual(restored.remaining_ids, ('c3',))
        self.assertEqual(result['implementation_test'],
                         render_contract(restored, 'implementation:decide'))
