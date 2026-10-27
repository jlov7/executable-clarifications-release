import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from executable_clarifications.core import ClarificationError
from executable_clarifications.policy import PolicySession, validate_policy
from executable_clarifications.session import SAFE_INTEGER, canonical, render_contract


def loan():
    def rule(op):
        return {'and': [{'field': 'score', 'op': op, 'value': 80},
                        {'field': 'category', 'op': '!=', 'value': 'blocked'}]}
    return {'schema': 'executable-clarifications/policy-v1',
            'fields': {'score': 'integer', 'accommodation': 'boolean',
                       'category': {'enum': ['ordinary', 'supervised', 'blocked']}},
            'candidates': [{'id': 'inclusive', 'rule': rule('>=')},
                           {'id': 'exclusive', 'rule': rule('>')}],
            'cases': [{'id': 'boundary', 'input': {
                'score': 80, 'accommodation': False, 'category': 'ordinary'}}]}


class Suggestions(unittest.TestCase):
    @staticmethod
    def interaction():
        spec = loan()
        spec['fields']['storm'] = 'boolean'
        spec['cases'][0]['input']['storm'] = False
        return spec

    def test_finite_grid_includes_four_field_changes_and_reports_unique_coverage(self):
        spec = self.interaction()
        spec['cases'].append(dict(spec['cases'][0], id='duplicate'))
        original = copy.deepcopy(spec)
        result = PolicySession(spec).suggest_cases()
        self.assertIn({'score': 79, 'accommodation': True, 'category': 'blocked', 'storm': True},
                      [c['input'] for c in result['added_cases']])
        coverage = result['coverage']
        self.assertEqual(coverage['domains'], {'score': [79, 80, 81], 'accommodation': [False, True],
                                              'category': ['blocked', 'ordinary', 'supervised'],
                                              'storm': [False, True]})
        self.assertEqual(coverage['total_combinations'], '36')
        self.assertEqual(coverage['covered_combinations'], '36')
        self.assertEqual(coverage['omitted_combinations'], '0')
        self.assertTrue(coverage['finite_domain_complete'])
        self.assertFalse(coverage['truncated'])
        self.assertEqual(len(result['added_cases']), 35)
        self.assertEqual(spec, original)

    def test_large_grid_reports_exact_partial_coverage_and_retains_boundary_priority(self):
        result = PolicySession(self.large()).suggest_cases()
        coverage = result['coverage']
        unique = {canonical(c['input']) for c in result['policy']['cases']}
        self.assertEqual(coverage['total_combinations'], str(3 * 3 * 2 ** 14))
        self.assertEqual(coverage['covered_combinations'], str(len(unique)))
        self.assertEqual(int(coverage['omitted_combinations']), int(coverage['total_combinations']) - len(unique))
        self.assertFalse(coverage['finite_domain_complete'])
        self.assertTrue(coverage['truncated'])
        self.assertIn(dict(self.large()['cases'][0]['input'], score=79),
                      [c['input'] for c in result['added_cases']])

    @staticmethod
    def complete_at_cap():
        return {'schema': 'executable-clarifications/policy-v1', 'fields': {'flag': 'boolean'},
                'candidates': [{'id': name, 'rule': {'field': 'flag', 'op': '==', 'value': True}}
                               for name in ('a', 'b')],
                'cases': [{'id': 'seed' + str(i), 'input': {'flag': bool(i % 2)}} for i in range(256)]}

    @staticmethod
    def enum_grid():
        values = [str(i) for i in range(32)]
        return {'schema': 'executable-clarifications/policy-v1',
                'fields': {'field' + str(i): {'enum': values} for i in range(16)},
                'candidates': [{'id': name, 'rule': {'field': 'field0', 'op': '==', 'value': '0'}}
                               for name in ('a', 'b')],
                'cases': [{'id': 'seed', 'input': {'field' + str(i): '0' for i in range(16)}}]}

    def test_complete_existing_grid_at_case_cap_and_oversized_grid_counts(self):
        coverage = PolicySession(self.complete_at_cap()).suggest_cases()['coverage']
        self.assertEqual(coverage['covered_combinations'], '2')
        self.assertTrue(coverage['finite_domain_complete'])
        self.assertFalse(coverage['truncated'])
        coverage = PolicySession(self.enum_grid()).suggest_cases()['coverage']
        self.assertEqual(coverage['total_combinations'], str(32 ** 16))
        self.assertEqual(coverage['omitted_combinations'], str(32 ** 16 - 256))
        self.assertFalse(coverage['finite_domain_complete'])

    def test_narrowed_session_suggests_unlabeled_exception_without_changing_original(self):
        s = PolicySession(loan()); s.answer(s.question()['id'], True)
        original = s.export_record()
        result = s.suggest_cases()
        self.assertEqual(s.export_record(), original)
        added = result['added_cases']
        target = {'score': 79, 'accommodation': True, 'category': 'ordinary'}
        self.assertIn(target, [x['input'] for x in added])
        self.assertTrue(all(set(x) == {'id', 'input'} for x in added))
        revised = PolicySession(result['policy'])
        self.assertEqual(revised.examples(), [])
        self.assertNotEqual(revised._version, s._version)
        revised.reconfirm(original, 'boundary')
        case = next(x for x in added if x['input'] == target)
        self.assertTrue(all(v is False for v in revised._table[case['id']].values()))
        revised.label_case(case['id'], True)
        self.assertEqual(revised.status, 'NO_CANDIDATE_MATCH')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); contract = root / 'test_contract.py'
            contract.write_text(render_contract(revised, 'implementation:decide'))
            for expression, expected in [
                ('x["category"] != "blocked" and x["score"] >= 80', 1),
                ('x["category"] != "blocked" and (x["score"] >= 80 or x["accommodation"])', 0)]:
                (root / 'implementation.py').write_text('def decide(x):\n    return ' + expression + '\n')
                run = subprocess.run([sys.executable, '-B', str(contract)], cwd=root,
                                     capture_output=True, text=True, timeout=10, check=False)
                self.assertEqual(run.returncode, expected, run.stderr)

    def test_exact_python_javascript_suggestion_revision_and_contract_parity(self):
        duplicate = self.interaction()
        duplicate['cases'].append(dict(duplicate['cases'][0], id='duplicate'))
        for spec in [loan(), self.extremes(), self.large(), duplicate, self.complete_at_cap(), self.enum_grid()]:
            with self.subTest(fields=spec['fields']):
                s = PolicySession(spec); result = s.suggest_cases()
                run = subprocess.run(['node', str(Path(__file__).with_name('suggestion-parity.js'))],
                                     input=canonical(spec), capture_output=True, text=True, timeout=20, check=False)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(json.loads(run.stdout), result)
                self.assertEqual(s.suggest_cases(), result)
                self.assertEqual(validate_policy(result['policy']), result['policy'])
                inputs = [canonical(c['input']) for c in result['policy']['cases']]
                seed_inputs = {canonical(c['input']) for c in spec['cases']}
                self.assertEqual(len(set(inputs)), len(seed_inputs) + len(result['added_cases']))

    @staticmethod
    def extremes():
        return {'schema': 'executable-clarifications/policy-v1', 'fields': {'x': 'integer'},
                'candidates': [{'id': 'a', 'rule': {'field': 'x', 'op': 'in', 'value': [-SAFE_INTEGER, SAFE_INTEGER]}},
                               {'id': 'b', 'rule': {'field': 'x', 'op': '>=', 'value': SAFE_INTEGER}}],
                'cases': [{'id': 'suggested_0001', 'input': {'x': 0}}]}

    @staticmethod
    def large():
        spec = loan()
        for i in range(13):
            spec['fields']['flag' + str(i)] = 'boolean'
            spec['cases'][0]['input']['flag' + str(i)] = False
        return spec

    def test_limits_dedup_id_collisions_all_agree_and_invalid_boundaries(self):
        spec = self.extremes(); result = PolicySession(spec).suggest_cases()
        self.assertTrue(all(abs(c['input']['x']) <= SAFE_INTEGER for c in result['added_cases']))
        self.assertNotIn('suggested_0001', [c['id'] for c in result['added_cases']])
        full = loan(); full['cases'] = [{'id': 'case' + str(i), 'input': {
            'score': i, 'accommodation': False, 'category': 'ordinary'}} for i in range(256)]
        result = PolicySession(full).suggest_cases()
        self.assertEqual(result['added_cases'], [])
        self.assertTrue(result['coverage']['truncated'])
        agree = loan(); agree['candidates'][1]['rule'] = copy.deepcopy(agree['candidates'][0]['rule'])
        session = PolicySession(agree)
        self.assertIsNone(session.question())
        self.assertGreater(len(session.suggest_cases()['added_cases']), 0)
        bad = loan(); bad['cases'][0]['input']['score'] = True
        with self.assertRaises(ClarificationError): PolicySession(bad).suggest_cases()

    def test_attempt_and_byte_caps_match_javascript_without_relaxing_policy_limits(self):
        attempts = self.large()
        attempts['cases'] = [dict(attempts['cases'][0], id='seed' + str(i)) for i in range(64)]
        byte_bound = loan()
        for i in range(13):
            byte_bound['fields']['category' + str(i)] = {'enum': ['a' * 64, 'b' * 64]}
            byte_bound['cases'][0]['input']['category' + str(i)] = 'a' * 64
        seed = byte_bound['cases'][0]
        while len(canonical(byte_bound).encode()) < 130000:
            byte_bound['cases'].append({'id': 'seed' + str(len(byte_bound['cases'])),
                                       'input': dict(seed['input'])})
        for spec, reason in [(attempts, 'attempt-limit'), (byte_bound, 'policy-byte-limit')]:
            result = PolicySession(spec).suggest_cases()
            self.assertEqual(result['coverage']['stop_reason'], reason)
            self.assertTrue(result['coverage']['truncated'])
            self.assertLessEqual(result['coverage']['attempts'], 4096)
            self.assertLessEqual(len(result['policy']['cases']), 256)
            self.assertLessEqual(len(canonical(result['policy']).encode()), 131072)
            run = subprocess.run(['node', str(Path(__file__).with_name('suggestion-parity.js'))],
                                 input=canonical(spec), capture_output=True, text=True, timeout=20, check=False)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout), result)

    def test_cli_preview_export_and_explicit_labels_never_execute_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'policy.json'; out = root / 'suggested.json'
            source.write_text(canonical(loan()))
            run = subprocess.run([sys.executable, '-m', 'executable_clarifications.cli',
                '--policy', str(source), '--answer', 'true', '--suggest-cases', '--export-policy', str(out)],
                capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(run.returncode, 0, run.stderr)
            data = json.loads(run.stdout)
            self.assertEqual(data['suggestions']['policy'], json.loads(out.read_text()))
            self.assertEqual(len(data['observed_examples']), 1)
            self.assertEqual(len(PolicySession(json.loads(out.read_text())).examples()), 0)
            run = subprocess.run([sys.executable, '-m', 'executable_clarifications.cli',
                '--policy', str(out), '--label-case', 'boundary=true', '--target', 'never_import_this:decide',
                '--export-test', str(root / 'contract.py')], capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('NOT RUN', json.loads(run.stdout)['execution'])
            repeat = subprocess.run([sys.executable, '-m', 'executable_clarifications.cli',
                '--policy', str(source), '--suggest-cases', '--export-policy', str(out)],
                capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(repeat.returncode, 2)


if __name__ == '__main__':
    unittest.main()
