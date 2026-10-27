import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from executable_clarifications.core import ClarificationError
from executable_clarifications.examples import ExampleSet
from executable_clarifications.policy import load_json
from executable_clarifications.session import canonical, render_contract


def supplied():
    return {'schema': 'executable-clarifications/example-set-v1',
            'fields': {'days': 'integer', 'exception': 'boolean',
                       'kind': {'enum': ['ordinary', 'blocked']}},
            'examples': [
                {'id': 'boundary', 'input': {'days': 30, 'exception': False, 'kind': 'ordinary'}, 'expected': True},
                {'id': 'outside', 'input': {'days': 47, 'exception': True, 'kind': 'ordinary'}, 'expected': True},
                {'id': 'blocked', 'input': {'days': 2, 'exception': True, 'kind': 'blocked'}, 'expected': False}]}


def candidates():
    return {'schema': 'executable-clarifications/policy-v1', 'fields': supplied()['fields'],
            'candidates': [{'id': 'inclusive', 'rule': {'field': 'days', 'op': '<=', 'value': 30}},
                           {'id': 'exclusive', 'rule': {'field': 'days', 'op': '<', 'value': 30}}],
            'cases': [{'id': 'seed', 'input': supplied()['examples'][0]['input']}]}


class KnownExamples(unittest.TestCase):
    def test_confirmation_export_and_strict_resume(self):
        source = supplied(); s = ExampleSet(source)
        self.assertEqual(s.status, 'PENDING_REVIEW')
        with self.assertRaises(ClarificationError): render_contract(s, 'implementation:decide')
        s.confirm(); self.assertEqual(s.status, 'REVIEWED_EXAMPLES')
        self.assertEqual([x['input'] for x in s.examples()], [x['input'] for x in source['examples']])
        record = s.export_record()
        self.assertEqual(ExampleSet.from_record(load_json(canonical(record))).export_record(), record)
        for key, value in [('version_digest', '0'*64), ('confirmed', 1), ('scope', 'complete')]:
            bad = copy.deepcopy(record); bad[key] = value
            with self.assertRaises(ClarificationError): ExampleSet.from_record(bad)
        bad = copy.deepcopy(record); bad['example_set']['examples'][0]['expected'] = False
        with self.assertRaises(ClarificationError): ExampleSet.from_record(bad)
        changed = copy.deepcopy(source); changed['examples'][0]['input']['days'] = 31
        newer = ExampleSet(changed)
        self.assertNotEqual(newer._version, s._version)
        self.assertEqual(newer.status, 'PENDING_REVIEW')
        self.assertEqual(source, supplied())

    def test_duplicates_contradictions_and_types_reject_before_mutation(self):
        s = ExampleSet(supplied()); s.confirm(); original = s.export_record()
        for change in ['duplicate', 'contradiction', 'id', 'integer', 'boolean', 'enum', 'unknown', 'empty', 'many']:
            bad = supplied()
            if change in ('duplicate', 'contradiction'):
                row = copy.deepcopy(bad['examples'][0]); row['id'] = 'another'
                if change == 'contradiction': row['expected'] = False
                bad['examples'].append(row)
            elif change == 'id': bad['examples'][1]['id'] = 'boundary'
            elif change == 'integer': bad['examples'][0]['input']['days'] = True
            elif change == 'boolean': bad['examples'][0]['expected'] = 1
            elif change == 'enum': bad['examples'][0]['input']['kind'] = 'unknown'
            elif change == 'unknown': bad['labels'] = {}
            elif change == 'empty': bad['examples'] = []
            else: bad['examples'] *= 86
            with self.subTest(change=change), self.assertRaises(ClarificationError): ExampleSet(bad)
            self.assertEqual(s.export_record(), original)
        for value in [9007199254740992, float('inf'), 1.0, None]:
            bad = supplied(); bad['examples'][0]['input']['days'] = value
            with self.assertRaises(ClarificationError): ExampleSet(bad)
        for text in ['{"schema":1,"schema":2}', '{"__proto__":{}}', '{"x":1e2}', '['*18+'0'+']'*18, ' '*262145]:
            with self.assertRaises(ClarificationError): load_json(text)

    def test_bounded_maximum_and_defensive_copies(self):
        source = supplied(); source['examples'] = [{'id': f'case{i}', 'input': {'days': i, 'exception': False, 'kind': 'ordinary'}, 'expected': True} for i in range(256)]
        s = ExampleSet(source); source['examples'][0]['expected'] = False; s.confirm()
        self.assertIs(s.examples()[0]['expected'], True)
        record = s.export_record(); record['example_set']['examples'][0]['expected'] = False
        self.assertIs(s.examples()[0]['expected'], True)

    def test_read_only_mismatch_audit_and_compatible_vocabulary(self):
        s = ExampleSet(supplied())
        with self.assertRaises(ClarificationError): s.audit(candidates())
        s.confirm(); original = s.export_record(); policy = candidates(); untouched = copy.deepcopy(policy)
        report = s.audit(policy)
        self.assertEqual(report['status'], 'NO_CANDIDATE_MATCH')
        self.assertEqual({r['candidate_id']: r['mismatch_ids'] for r in report['candidates']},
                         {'inclusive': ['outside', 'blocked'], 'exclusive': ['boundary', 'outside', 'blocked']})
        self.assertEqual(len(report['matrix']), 3)
        self.assertEqual(s.export_record(), original); self.assertEqual(policy, untouched)
        policy['fields']['other'] = 'integer'
        policy['cases'][0]['input']['other'] = 1
        with self.assertRaises(ClarificationError): s.audit(policy)

    def test_javascript_record_audit_contract_and_invalid_parity(self):
        s = ExampleSet(supplied()); s.confirm()
        bad = supplied(); bad['examples'].append(dict(bad['examples'][0], id='duplicate'))
        process = subprocess.run(['node', str(Path(__file__).with_name('examples-parity.js'))], input=canonical({'example_set': supplied(), 'policy': candidates(), 'bad': bad}), text=True, capture_output=True, check=True)
        result = json.loads(process.stdout)
        self.assertEqual(result['record'], s.export_record())
        self.assertEqual(result['audit'], s.audit(candidates()))
        self.assertEqual(result['contract'], render_contract(s, 'implementation:decide'))
        self.assertTrue(result['refused_pending']); self.assertTrue(result['refused_bad'])

    def test_cli_confirmation_resume_exclusive_output_and_no_candidate_setup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root/'examples.json'; source.write_text(canonical(supplied()))
            command = [sys.executable, '-m', 'executable_clarifications.cli']
            def run(*args): return subprocess.run(command+list(map(str,args)), capture_output=True, text=True, check=False)
            blocked = root/'blocked.py'
            self.assertEqual(run('--examples',source,'--target','implementation:decide','--export-test',blocked).returncode,2)
            self.assertFalse(blocked.exists())
            saved, contract = root/'record.json', root/'contract.py'
            result = run('--examples',source,'--confirm-examples','--save-session',saved,'--target','implementation:decide','--export-test',contract)
            self.assertEqual(result.returncode,0,result.stderr)
            s = ExampleSet.from_record(load_json(saved.read_text()))
            self.assertEqual(contract.read_text(),render_contract(s,'implementation:decide'))
            resumed = run('--resume',saved); self.assertEqual(json.loads(resumed.stdout)['session'],s.export_record())
            self.assertEqual(run('--examples',source,'--confirm-examples','--save-session',saved).returncode,2)
            self.assertEqual(run('--examples',source,'--answer','true').returncode,2)
            self.assertEqual(run('--confirm-examples').returncode,2)
            self.assertEqual(run('--examples',source,'--confirm-examples','--save-session',root/'no-write.json','--target','bad;target','--export-test',root/'no.py').returncode,2)
            self.assertFalse((root/'no-write.json').exists())
