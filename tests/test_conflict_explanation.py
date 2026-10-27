"""A deletion-minimal conflict explains a finite candidate gap, not human intent."""
import copy
import json
import subprocess
import unittest
from pathlib import Path

from executable_clarifications.conflicts import explain_conflict
from executable_clarifications.core import ClarificationError
from executable_clarifications.examples import ExampleSet


def examples():
    return {'schema': 'executable-clarifications/example-set-v1', 'fields': {'x': 'integer'},
            'examples': [{'id': 'one', 'input': {'x': 1}, 'expected': False},
                         {'id': 'two', 'input': {'x': 2}, 'expected': False},
                         {'id': 'irrelevant', 'input': {'x': 3}, 'expected': False}]}


def policy():
    return {'schema': 'executable-clarifications/policy-v1', 'fields': {'x': 'integer'},
            'candidates': [{'id': 'is_one', 'rule': {'field': 'x', 'op': '==', 'value': 1}},
                           {'id': 'is_two', 'rule': {'field': 'x', 'op': '==', 'value': 2}}],
            'cases': [{'id': 'start', 'input': {'x': 1}}]}


class ConflictExplanationTests(unittest.TestCase):
    def test_javascript_parity_for_every_small_labeling_and_reordered_inputs(self):
        cases = []
        for mask in range(64):
            source = examples()
            source['examples'] = [{'id': f'row{i}', 'input': {'x': i},
                                   'expected': bool(mask & (1 << i))} for i in range(6)]
            candidates = policy()
            candidates['candidates'] = [
                {'id': f'lt{i}', 'rule': {'field': 'x', 'op': '<', 'value': i}}
                for i in range(1, 5)]
            if mask % 2:
                source['examples'].reverse()
                candidates['candidates'].reverse()
            cases.append({'examples': source, 'policy': candidates})
        process = subprocess.run(['node', str(Path(__file__).with_name('conflict-parity.js'))],
                                 input=json.dumps(cases), capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        expected = []
        for case in cases:
            session = ExampleSet(case['examples']); session.confirm()
            expected.append(explain_conflict(session, case['policy']))
        self.assertEqual(json.loads(process.stdout), expected)

    def test_deletion_minimal_does_not_mean_globally_smallest(self):
        source = {'schema': 'executable-clarifications/example-set-v1',
                  'fields': {'x': 'integer'}, 'examples': [
                      {'id': name, 'input': {'x': i}, 'expected': False}
                      for i, name in enumerate('abcde')]}
        candidates = policy()
        candidates['candidates'] = [
            {'id': 'first', 'rule': {'field': 'x', 'op': 'in', 'value': [0, 2]}},
            {'id': 'second', 'rule': {'field': 'x', 'op': 'in', 'value': [0, 3]}},
            {'id': 'third', 'rule': {'field': 'x', 'op': 'in', 'value': [1, 4]}}]
        session = ExampleSet(source); session.confirm()
        report = explain_conflict(session, candidates)
        self.assertEqual(report['core_example_ids'], ['c', 'd', 'e'])
        smaller = copy.deepcopy(source); smaller['examples'] = smaller['examples'][:2]
        session = ExampleSet(smaller); session.confirm()
        self.assertEqual(explain_conflict(session, candidates)['status'], 'NO_OFFERED_CANDIDATE_FITS')
        self.assertFalse(report['minimum_cardinality_claimed'])

    def test_minimal_conflict_has_a_witness_for_each_member(self):
        session = ExampleSet(examples()); session.confirm()
        report = explain_conflict(session, policy())
        self.assertEqual(report['status'], 'NO_OFFERED_CANDIDATE_FITS')
        self.assertEqual(report['core_example_ids'], ['one', 'two'])
        self.assertEqual(report['removal_witnesses'], [
            {'removed_example_id': 'one', 'fitting_candidate': 'is_one'},
            {'removed_example_id': 'two', 'fitting_candidate': 'is_two'}])
        self.assertEqual(report['candidate_eliminations'], [
            {'candidate_id': 'is_one', 'mismatched_core_example': 'one'},
            {'candidate_id': 'is_two', 'mismatched_core_example': 'two'}])
        self.assertFalse(report['minimum_cardinality_claimed'])
        self.assertFalse(report['labels_judged_incorrect'])

    def test_a_fit_never_manufactures_a_conflict(self):
        source = examples(); source['examples'] = source['examples'][:1]
        session = ExampleSet(source); session.confirm()
        report = explain_conflict(session, policy())
        self.assertEqual(report['status'], 'OFFERED_CANDIDATE_FITS')
        self.assertEqual(report['fitting_candidates'], ['is_two'])
        self.assertEqual(report['core_example_ids'], [])
        self.assertEqual(report['removal_witnesses'], [])

    def test_order_independent_core_and_no_input_mutation(self):
        source, candidates = examples(), policy()
        session = ExampleSet(source); session.confirm()
        saved = copy.deepcopy((session.export_record(), candidates))
        expected = explain_conflict(session, candidates)
        source['examples'].reverse(); candidates['candidates'].reverse()
        reversed_session = ExampleSet(source); reversed_session.confirm()
        actual = explain_conflict(reversed_session, candidates)
        for field in ('core_example_ids', 'removal_witnesses', 'candidate_eliminations'):
            self.assertEqual(expected[field], actual[field])
        self.assertEqual(session.export_record(), saved[0])
        self.assertEqual(list(reversed(candidates['candidates'])), saved[1]['candidates'])

    def test_confirmation_and_field_vocabulary_still_required(self):
        session = ExampleSet(examples())
        with self.assertRaises(ClarificationError):
            explain_conflict(session, policy())
        session.confirm(); changed = policy(); changed['fields']['x'] = 'boolean'
        with self.assertRaises(ClarificationError):
            explain_conflict(session, changed)

    def test_explanation_does_not_change_labels_or_candidate_definitions(self):
        session = ExampleSet(examples()); session.confirm()
        report = explain_conflict(session, policy())
        report['core_example_ids'].clear()
        self.assertEqual(len(session.examples()), 3)
        self.assertTrue(all(row['expected'] is False for row in session.examples()))
        self.assertEqual(explain_conflict(session, policy())['core_example_ids'], ['one', 'two'])

    def test_all_small_labelings_have_valid_elimination_and_removal_witnesses(self):
        from executable_clarifications.policy import evaluate
        candidates = policy()
        candidates['candidates'] = [{'id': f'lt{i}', 'rule': {'field': 'x', 'op': '<', 'value': i}}
                                    for i in range(1, 5)]
        for mask in range(64):
            source = examples()
            source['examples'] = [{'id': f'row{i}', 'input': {'x': i}, 'expected': bool(mask & (1 << i))}
                                  for i in range(6)]
            session = ExampleSet(source); session.confirm()
            report = explain_conflict(session, candidates)
            if report['status'] == 'OFFERED_CANDIDATE_FITS':
                continue
            core = [r for r in source['examples'] if r['id'] in report['core_example_ids']]
            def fits(rows):
                return [c['id'] for c in candidates['candidates'] if all(
                    evaluate(c['rule'], row['input']) is row['expected'] for row in rows)]
            with self.subTest(mask=mask):
                self.assertFalse(fits(core))
                for witness in report['removal_witnesses']:
                    remaining = [r for r in core if r['id'] != witness['removed_example_id']]
                    self.assertIn(witness['fitting_candidate'], fits(remaining))

    def test_cli_explains_without_rewriting_or_running_any_target(self):
        import json
        import os
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, candidate = root / 'examples.json', root / 'policy.json'
            source.write_text(json.dumps(examples())); candidate.write_text(json.dumps(policy()))
            command = [sys.executable, '-m', 'executable_clarifications.cli', '--examples', str(source),
                       '--confirm-examples', '--audit-policy', str(candidate), '--explain-conflict']
            process = subprocess.run(command, capture_output=True, text=True, timeout=15,
                                     env=os.environ.copy(), check=False)
            self.assertEqual(process.returncode, 0, process.stderr)
            report = json.loads(process.stdout)
            self.assertEqual(report['conflict_explanation']['core_example_ids'], ['one', 'two'])
            self.assertEqual(report['status'], 'REVIEWED_EXAMPLES')
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['examples.json', 'policy.json'])

    def test_cli_refuses_missing_audit_pending_labels_and_supplied_code_before_outputs(self):
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, candidate = root / 'examples.json', root / 'policy.json'
            output = root / 'review.json'
            source.write_text(json.dumps(examples())); candidate.write_text(json.dumps(policy()))
            base = [sys.executable, '-m', 'executable_clarifications.cli', '--examples', str(source),
                    '--explain-conflict', '--save-session', str(output)]
            for options, message in [([], 'requires --audit-policy'),
                                     (['--audit-policy', str(candidate)], 'confirm the supplied examples')]:
                result = subprocess.run(base + options, capture_output=True, text=True,
                                        timeout=15, check=False)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(message, result.stderr)
                self.assertFalse(output.exists())
            marker = root / 'executed'
            candidate.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
            result = subprocess.run(base + ['--confirm-examples', '--audit-policy', str(candidate)],
                                    capture_output=True, text=True, timeout=15, check=False)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse(output.exists())
