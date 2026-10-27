import copy
import json
import subprocess
import unittest
from pathlib import Path

from executable_clarifications.policy import PolicySession
from executable_clarifications.session import render_contract


def policy():
    return {'schema': 'executable-clarifications/policy-v1', 'fields': {'x': 'integer'},
            'candidates': [{'id': 'a', 'rule': {'field': 'x', 'op': '==', 'value': 0}},
                           {'id': 'b', 'rule': {'field': 'x', 'op': '!=', 'value': 0}}],
            'cases': [{'id': 'c', 'input': {'x': 0}}]}


class ReturnedState(unittest.TestCase):
    def test_review_inputs_leave_record_digest_and_question_unchanged(self):
        session = PolicySession(policy())
        record, question = session.export_record(), session.question()
        session.case_review()[0]['input']['x'] = 99
        self.assertEqual(session.export_record(), record)
        self.assertEqual(session.question(), question)
        self.assertEqual(PolicySession.from_record(record).export_record(), record)

    def test_review_predictions_leave_labels_contract_and_replay_unchanged(self):
        session, control = PolicySession(policy()), PolicySession(policy())
        session.case_review()[0]['predictions']['a'] = False
        session.label_case('c', True); control.label_case('c', True)
        self.assertEqual(session.remaining_ids, control.remaining_ids)
        self.assertEqual(session.case_review(), control.case_review())
        self.assertEqual(session.export_record(), control.export_record())
        self.assertEqual(render_contract(session, 'implementation:decide'),
                         render_contract(control, 'implementation:decide'))
        self.assertEqual(PolicySession.from_record(session.export_record()).remaining_ids,
                         session.remaining_ids)

    def test_preview_inputs_leave_original_examples_and_contract_unchanged(self):
        session = PolicySession(policy()); session.label_case('c', True)
        record, examples = session.export_record(), session.examples()
        contract = render_contract(session, 'implementation:decide')
        revised = copy.deepcopy(policy()); revised['cases'][0]['input']['x'] = 1
        session.revision_preview(revised)['pending'][0]['input']['x'] = 99
        self.assertEqual(session.export_record(), record)
        self.assertEqual(session.examples(), examples)
        self.assertEqual(render_contract(session, 'implementation:decide'), contract)
        self.assertEqual(PolicySession.from_record(record).case_review(), session.case_review())

    def test_javascript_returned_artifacts(self):
        run = subprocess.run(['node', str(Path(__file__).with_name('returned-state.js'))],
                             input=json.dumps(policy()), text=True, capture_output=True, timeout=10, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['checks'], 8)
