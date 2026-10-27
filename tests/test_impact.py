import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from executable_clarifications.core import ClarificationError
from executable_clarifications.policy import PolicySession
from executable_clarifications.session import canonical


def policies():
    old = {'schema': 'executable-clarifications/policy-v1',
           'fields': {'score': 'integer', 'trainee': 'boolean', 'mode': {'enum': ['desk', 'remote']}},
           'candidates': [
               {'id': 'access', 'rule': {'field': 'score', 'op': '>=', 'value': 80}},
               {'id': 'other', 'rule': {'field': 'score', 'op': '<=', 'value': 5}}],
           'cases': [{'id': 'low', 'input': {'score': 20, 'trainee': False, 'mode': 'desk'}},
                     {'id': 'high', 'input': {'score': 100, 'trainee': False, 'mode': 'desk'}}]}
    new = copy.deepcopy(old)
    new['candidates'][0]['rule'] = {'or': [
        {'field': 'score', 'op': '>', 'value': 80},
        {'field': 'trainee', 'op': '==', 'value': True}]}
    return old, new


class PolicyImpact(unittest.TestCase):
    def compare(self, old, new, observed=()):
        from executable_clarifications.impact import compare_policies
        return compare_policies(old, new, observed_case_ids=observed)

    def parity(self, old, new, observed=()):
        run = subprocess.run(['node', str(Path(__file__).with_name('impact-parity.js'))],
                             input=json.dumps({'baseline': old, 'proposed': new, 'observed': observed}),
                             text=True, capture_output=True, timeout=20, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), self.compare(old, new, observed))

    def test_exception_and_boundary_missed_by_observed_cases_have_unlabelled_witnesses(self):
        old, new = policies()
        session = PolicySession(old)
        session.label_case('low', False); session.label_case('high', True)
        original = canonical(session.export_record())
        impact = session.revision_preview(new)['impact']
        item = impact['candidate_impacts'][0]
        self.assertEqual(item['candidate_id'], 'access')
        self.assertEqual((item['false_to_true_count'], item['true_to_false_count']), (14, 2))
        self.assertEqual((item['observed_false_to_true_count'], item['observed_true_to_false_count']), (0, 0))
        self.assertEqual(impact['coverage']['domains']['mode'], ['desk', 'remote'])
        self.assertEqual(impact['coverage']['baseline_unreferenced_fields'], ['mode', 'trainee'])
        self.assertEqual(impact['coverage']['unreferenced_fields'], ['mode'])
        self.assertEqual(impact['coverage']['checked_combinations'], '48')
        self.assertTrue(impact['coverage']['finite_domain_complete'])
        self.assertEqual({(w['before'], w['after']) for w in impact['witnesses']}, {(False, True), (True, False)})
        self.assertTrue(all(not w['exercised_by_observed_example'] and 'expected' not in w for w in impact['witnesses']))
        self.assertEqual(canonical(session.export_record()), original)
        self.assertEqual(PolicySession(new).examples(), [])
        self.parity(old, new, ['low', 'high'])

    def test_observed_change_is_distinct_from_new_witnesses_and_returned_state_is_detached(self):
        old, new = policies()
        exception = {'id': 'exception', 'input': {'score': 20, 'trainee': True, 'mode': 'desk'}}
        old['cases'].append(exception); new['cases'].append(copy.deepcopy(exception))
        report = self.compare(old, new, ['exception'])
        item = report['candidate_impacts'][0]
        self.assertEqual(item['observed_false_to_true_count'], 1)
        self.assertEqual(item['unobserved_false_to_true_count'], 13)
        self.assertEqual({w['exercised_by_observed_example'] for w in report['witnesses']}, {False, True})
        report['witnesses'][0]['input']['score'] = -999
        self.assertEqual(old['cases'][-1], exception)
        self.parity(old, new, ['exception'])

    def test_both_revisions_literals_seed_values_and_safe_integer_edges_participate(self):
        old, new = policies()
        new['candidates'][0]['rule'] = {'field': 'score', 'op': 'in', 'value': [70, 9007199254740991]}
        new['cases'][0]['input']['score'] = -9007199254740991
        report = self.compare(old, new)
        domain = report['coverage']['domains']['score']
        for value in [69, 70, 71, 79, 80, 81, -9007199254740991, -9007199254740990, 9007199254740990, 9007199254740991]:
            self.assertIn(value, domain)
        self.assertTrue(all(abs(v) <= 9007199254740991 for v in domain))
        self.parity(old, new)

    def test_structural_rewrite_is_unchanged_only_on_checked_inputs_and_ids_align(self):
        old, new = policies()
        leaf = copy.deepcopy(old['candidates'][0]['rule'])
        new['candidates'][0]['rule'] = {'or': [leaf, copy.deepcopy(leaf)]}
        new['fields']['mode']['enum'].reverse()
        new['candidates'].reverse()
        report = self.compare(old, new)
        self.assertTrue(report['compatible'])
        self.assertEqual(report['candidate_impacts'][0]['status'], 'unchanged-on-checked-inputs')
        self.assertEqual(report['witnesses'], [])
        self.assertNotIn('equivalent', report)
        new['candidates'][0]['id'] = 'added'
        report = self.compare(old, new)
        self.assertEqual(report['added_candidates'], ['added'])
        self.assertEqual(report['removed_candidates'], ['other'])
        self.assertEqual([c['candidate_id'] for c in report['candidate_impacts']], ['access'])
        self.parity(old, new)

    def test_incompatible_field_vocabulary_is_reported_without_coercion(self):
        old, new = policies()
        new['fields']['mode']['enum'].append('phone')
        report = self.compare(old, new)
        self.assertFalse(report['compatible'])
        self.assertEqual(report['incompatible_fields'][0]['field'], 'mode')
        self.assertIsNone(report['coverage'])
        self.assertEqual(report['candidate_impacts'], [])
        self.parity(old, new)
        new = copy.deepcopy(old); new['fields']['trainee'] = 'integer'
        for c in new['cases']: c['input']['trainee'] = 0
        self.assertFalse(self.compare(old, new)['compatible'])
        self.parity(old, new)
        for observed in [None, ['unknown'], ['low', 'low'], 'low']:
            with self.assertRaises(ClarificationError): self.compare(old, new, observed)
            run = subprocess.run(['node', str(Path(__file__).with_name('impact-parity.js'))],
                input=json.dumps({'baseline': old, 'proposed': new, 'observed': observed}),
                text=True, capture_output=True, timeout=10, check=False)
            self.assertNotEqual(run.returncode, 0)

    def test_large_domain_reports_exact_checked_omitted_and_witness_bounds(self):
        old, new = policies()
        for spec in (old, new):
            spec['fields'].update({f'flag{i}': 'boolean' for i in range(10)})
            for case in spec['cases']: case['input'].update({f'flag{i}': False for i in range(10)})
        report = self.compare(old, new)
        coverage = report['coverage']
        self.assertEqual(coverage['total_combinations'], str(48 * 2**10))
        self.assertEqual(coverage['checked_combinations'], '4096')
        self.assertEqual(coverage['omitted_combinations'], str(48 * 2**10 - 4096))
        self.assertEqual(coverage['stop_reasons'], ['input-limit'])
        self.assertFalse(coverage['finite_domain_complete'])
        self.assertLessEqual(len(report['witnesses']), 128)
        self.assertLessEqual(len(canonical(report).encode()), 1048576)
        self.assertEqual(report['output']['report_bytes'], len(canonical(report).encode()))
        self.assertLessEqual(coverage['attempts'], coverage['attempt_limit'])
        self.assertEqual(report['output']['omitted_change_pairs'], sum(c['false_to_true_count'] + c['true_to_false_count'] for c in report['candidate_impacts']) - len(report['witnesses']))
        self.parity(old, new)

    def test_added_removed_builtin_name_fields_are_explicit_null_in_both_runtimes(self):
        for name in ['toString', 'valueOf', 'hasOwnProperty']:
            old, new = policies()
            new['fields'][name] = 'boolean'
            for case in new['cases']: case['input'][name] = False
            for baseline, proposed in [(old, new), (new, old)]:
                report = self.compare(baseline, proposed)
                self.assertEqual(report['incompatible_fields'][0]['field'], name)
                self.assertIn(None, [report['incompatible_fields'][0]['baseline'], report['incompatible_fields'][0]['proposed']])
                self.parity(baseline, proposed)

    def test_domain_cap_retains_supplied_values_and_discloses_omitted_boundary_values(self):
        old, new = policies()
        for spec in (old, new):
            spec['candidates'] = [{'id': f'c{i:02}', 'rule': {'or': [
                {'field': 'score', 'op': 'in', 'value': [i*10000 + j*10 for j in range(32)]},
                {'field': 'trainee', 'op': '==', 'value': False}]}} for i in range(32)]
        report = self.compare(old, new)
        coverage = report['coverage']
        self.assertEqual(coverage['domain_sizes']['score']['retained_values'], 1024)
        self.assertGreater(coverage['domain_sizes']['score']['omitted_values'], 0)
        self.assertIn(100, coverage['domains']['score'])
        self.assertIn('domain-value-limit', coverage['stop_reasons'])
        self.parity(old, new)

    def test_cli_policy_and_resume_comparison_is_read_only_and_rejects_other_modes(self):
        old, new = policies()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            baseline, proposed, saved = [folder / name for name in ['baseline.json', 'proposed.json', 'session.json']]
            baseline.write_text(canonical(old)); proposed.write_text(canonical(new))
            session = PolicySession(old); session.label_case('low', False)
            original = canonical(session.export_record()); saved.write_text(original)
            command = [sys.executable, '-m', 'executable_clarifications.cli']
            for source in [['--policy', str(baseline)], ['--resume', str(saved)]]:
                run = subprocess.run(command + source + ['--compare-policy', str(proposed)], text=True, capture_output=True, timeout=10, check=False)
                self.assertEqual(run.returncode, 0, run.stderr)
                result = json.loads(run.stdout)
                self.assertEqual(result['policy_impact'], self.compare(old, new, ['low'] if source[0] == '--resume' else []))
                self.assertEqual(saved.read_text(), original)
            run = subprocess.run(command + ['--compare-policy', str(proposed)], text=True, capture_output=True, timeout=10, check=False)
            self.assertEqual(run.returncode, 2)
            self.assertIn('custom policy', run.stderr)
