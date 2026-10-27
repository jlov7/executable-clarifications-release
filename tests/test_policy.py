import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from executable_clarifications.core import ClarificationError


def fixture():
    return json.loads((Path(__file__).parent / 'fixtures/refund_policy.json').read_text())


class CustomPolicy(unittest.TestCase):
    def engine(self):
        from executable_clarifications.policy import PolicySession, load_json
        return PolicySession, load_json

    def test_multifield_session_replays_and_undoes(self):
        Session, _ = self.engine()
        session = Session(fixture())
        while session.question():
            q = session.question()
            x = q['input']
            session.answer(q['id'], (x['days'] <= 30 and x['unopened']) or x['reason'] == 'defective')
        self.assertEqual(session.remaining_ids, ('refund',))
        record = session.export_record()
        self.assertEqual(Session.from_record(record).export_record(), record)
        session.undo()
        self.assertEqual(len(session.examples()), len(record['decisions']) - 1)
        self.assertIsNotNone(session.question())

    def test_changed_inputs_and_tampered_history_rejected(self):
        Session, _ = self.engine()
        session = Session(fixture())
        session.answer(session.question()['id'], True)
        record = session.export_record()
        for mutate in (lambda r: r['policy']['cases'][0]['input'].update(days=99),
                       lambda r: r['decisions'][0].update(question_id='fake'),
                       lambda r: r.update(extra=True)):
            bad = copy.deepcopy(record)
            mutate(bad)
            with self.assertRaises(ClarificationError):
                Session.from_record(bad)

    def test_neither_blocks_export_and_undo_recovers(self):
        from executable_clarifications.session import render_contract
        Session, _ = self.engine()
        s = Session(fixture())
        s.answer(s.question()['id'], None)
        self.assertEqual(s.status, 'UNRESOLVED')
        with self.assertRaises(ClarificationError): render_contract(s, 'implementation:decide')
        s.undo()
        self.assertEqual(s.status, 'OPEN')

    def test_validation_limits_and_unknown_values(self):
        Session, _ = self.engine()
        mutations = [lambda p: p.update(code='alert(1)'),
                     lambda p: p['fields'].update(__proto__='boolean'),
                     lambda p: p['cases'][0]['input'].update(days=True),
                     lambda p: p['cases'][0]['input'].update(unknown=1),
                     lambda p: p['cases'][0]['input'].pop('reason'),
                     lambda p: p['candidates'].append(p['candidates'][0]),
                     lambda p: p['candidates'][0].update(id='<img onerror=alert(1)>'),
                     lambda p: p['candidates'][0].update(rule={'eval':'x'}),
                     lambda p: p['cases'][0]['input'].update(reason='<script>'),
                     lambda p: p['candidates'][0].update(rule={'and': []}),
                     lambda p: p['cases'].extend(p['cases'] * 100)]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                bad = fixture(); mutation(bad)
                with self.assertRaises(ClarificationError): Session(bad)

    def test_strict_json_duplicate_keys_depth_and_bytes(self):
        _, load = self.engine()
        for value in ('{"a":1,"a":2}', '{"__proto__":1}', ' ' * 262145,
                      '[' * 30 + '0' + ']' * 30, '{"x":NaN}'):
            with self.subTest(value=value[:30]), self.assertRaises(ClarificationError):
                load(value)

    def test_same_contract_accepts_reviewed_and_rejects_boolean_boundary_errors(self):
        from executable_clarifications.session import render_contract
        Session, _ = self.engine()
        s = Session(fixture())
        while s.question():
            q = s.question(); x = q['input']
            s.answer(q['id'], (x['days'] <= 30 and x['unopened']) or x['reason'] == 'defective')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'contract.py').write_text(render_contract(s, 'implementation:decide'))
            for rule, expected in [('(x["days"] <= 30 and x["unopened"]) or x["reason"] == "defective"', 0),
                                   ('x["days"] <= 30 and x["unopened"] and x["reason"] == "defective"', 1),
                                   ('(x["days"] < 30 and x["unopened"]) or x["reason"] == "defective"', 1)]:
                (root / 'implementation.py').write_text('def decide(x):\n    return ' + rule + '\n')
                run = subprocess.run([sys.executable, '-B', str(root / 'contract.py')], cwd=root,
                                     capture_output=True, text=True, timeout=10, check=False)
                self.assertEqual(run.returncode, expected, run.stderr)

    def test_cli_custom_policy_save_resume_and_export(self):
        self.engine()
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / 'session.json'
            cmd = [sys.executable, '-m', 'executable_clarifications.cli']
            run = subprocess.run(cmd + ['--policy', str(Path(__file__).parent / 'fixtures/refund_policy.json'),
                                        '--answer', 'true', '--save-session', str(record)],
                                 capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(run.returncode, 0, run.stderr)
            resumed = subprocess.run(cmd + ['--resume', str(record), '--undo'],
                                     capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(json.loads(resumed.stdout)['session']['decisions'], [])


    def test_resource_limits_and_unknown_predicates_fail_closed(self):
        Session, _ = self.engine()
        deep = {'field': 'days', 'op': '<=', 'value': 30}
        for _ in range(7): deep = {'or': [deep, {'field':'unopened','op':'==','value':True}]}
        changes = [lambda p: p['candidates'][0].update(rule=deep),
                   lambda p: p['cases'].append(p['cases'][0]),
                   lambda p: p['candidates'][0].update(rule={'field':'days','op':'eval','value':30}),
                   lambda p: p['cases'][0]['input'].update(days=2**53),
                   lambda p: p['fields']['reason'].update(enum=['defective','defective']),
                   lambda p: p['candidates'][0].update(rule={'field':'reason','op':'<','value':'defective'})]
        for change in changes:
            bad=fixture(); change(bad)
            with self.assertRaises(ClarificationError): Session(bad)


    def test_cli_saved_near_byte_limit_policy_can_resume(self):
        from executable_clarifications.session import canonical
        leaf = {'field': 'x', 'op': '>', 'value': 0}
        rule = {'and': [{'or': [leaf] * 6} for _ in range(16)]}
        policy = {'schema': 'executable-clarifications/policy-v1', 'fields': {'x':'integer'},
                  'candidates': [{'id': f'candidate_{i:02d}', 'rule': rule} for i in range(32)],
                  'cases': [{'id':'one', 'input':{'x':1}}]}
        self.assertLessEqual(len(canonical(policy).encode()), 131072)
        with tempfile.TemporaryDirectory() as directory:
            source, saved = Path(directory) / 'policy.json', Path(directory) / 'saved.json'
            source.write_text(canonical(policy))
            cmd = [sys.executable, '-m', 'executable_clarifications.cli']
            first = subprocess.run(cmd + ['--policy', str(source), '--save-session', str(saved)],
                                   capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            resumed = subprocess.run(cmd + ['--resume', str(saved)],
                                     capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(resumed.returncode, 0,
                             f'saved {saved.stat().st_size} bytes: ' + resumed.stderr)
            self.assertLessEqual(saved.stat().st_size, 262144)
            self.assertEqual(json.loads(first.stdout)['session'], json.loads(resumed.stdout)['session'])

    def test_max_rule_depth_policy_record_and_cli_roundtrip(self):
        from executable_clarifications.session import canonical
        Session, load = self.engine()
        leaf = {'field':'x', 'op':'>', 'value':0}
        rule = leaf
        for _ in range(6): rule = {'or': [rule, leaf]}
        policy = {'schema': 'executable-clarifications/policy-v1', 'fields': {'x':'integer'},
                  'candidates': [{'id':'a', 'rule':rule}, {'id':'b', 'rule':leaf}],
                  'cases': [{'id':'one', 'input':{'x':1}}]}
        with self.subTest(boundary='API export/parse/restore'):
            session = Session(policy)
            record = session.export_record()
            self.assertEqual(Session.from_record(load(canonical(record))).export_record(), record)
        with self.subTest(boundary='CLI save/resume'), tempfile.TemporaryDirectory() as directory:
            source, saved = Path(directory) / 'policy.json', Path(directory) / 'saved.json'
            source.write_text(canonical(policy))
            cmd = [sys.executable, '-m', 'executable_clarifications.cli']
            first = subprocess.run(cmd + ['--policy', str(source), '--save-session', str(saved)],
                                   capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            resumed = subprocess.run(cmd + ['--resume', str(saved)],
                                     capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(json.loads(first.stdout)['session'], json.loads(resumed.stdout)['session'])
        # The extra envelope level must not relax ordinary JSON/policy depth limits.
        for value in ('[' * 17 + '0' + ']' * 17,
                  '{"schema":"executable-clarifications/policy-session-v1","extra":' + '[' * 17 + '0' + ']' * 17 + '}'):
            with self.assertRaises(ClarificationError): load(value)
