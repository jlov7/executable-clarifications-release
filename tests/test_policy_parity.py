import copy
import json
import subprocess
import unittest
from pathlib import Path

from executable_clarifications.core import ClarificationError
from executable_clarifications.policy import PolicySession, evaluate, load_json, validate_policy
from executable_clarifications.session import render_contract

ROOT = Path(__file__).resolve().parents[1]


class RuntimeParity(unittest.TestCase):
    def node(self, data):
        result = subprocess.run(['node', str(ROOT / 'tests/policy-parity.js')],
                                input=json.dumps(data), text=True, capture_output=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_all_refund_paths_match_python_and_export_bytes(self):
        spec = json.loads((ROOT / 'tests/fixtures/refund_policy.json').read_text())
        states = []
        def visit(session):
            q = session.question()
            states.append({'record': session.export_record(), 'question': q,
                           'status': session.status, 'examples': session.examples(),
                           'contract': render_contract(session, 'implementation:decide')
                           if session.status != 'UNRESOLVED' and session.examples() else None})
            if q:
                for answer in (False, True, None):
                    child = PolicySession.from_record(session.export_record())
                    child.answer(q['id'], answer); visit(child)
        visit(PolicySession(spec))
        self.assertEqual(self.node(spec), states)

    def test_all_comparisons_boolean_membership_shipping_and_safe_integer_extremes(self):
        spec = {'schema': 'executable-clarifications/policy-v1',
                'fields': {'total': 'integer', 'member': 'boolean'},
                'candidates': [{'id': 'c' + str(i), 'rule': {'field': 'total', 'op': op, 'value': 50}}
                               for i, op in enumerate(('==', '!=', '<', '<=', '>', '>='))] + [
                    {'id': 'shipping', 'rule': {'or': [
                        {'field': 'total', 'op': '>=', 'value': 50},
                        {'field': 'member', 'op': 'in', 'value': [True]}]}}],
                'cases': [{'id': 'x' + str(i), 'input': {'total': n, 'member': b}}
                          for i, (n,b) in enumerate(((-9007199254740991,False), (49,True),
                                                    (50,False), (51,False), (9007199254740991,True)))]}
        expected = [[False,True,True,True,False,False,False],
                    [False,True,True,True,False,False,True],
                    [True,False,False,True,False,True,True],
                    [False,True,False,False,True,True,True],
                    [False,True,False,False,True,True,True]]
        reviewed = validate_policy(spec)
        table = [[evaluate(c['rule'], x['input']) for c in reviewed['candidates']]
                 for x in reviewed['cases']]
        self.assertEqual(table, expected)
        self.assertEqual(self.node({'table': spec}), expected)
        node = self.node(spec)[0]
        python = PolicySession(spec)
        self.assertEqual(node['question'], python.question())
        self.assertEqual(node['record'], python.export_record())

    def test_malformed_and_xss_boundaries_match_in_both_runtimes(self):
        spec = json.loads((ROOT / 'tests/fixtures/refund_policy.json').read_text())
        bad = []
        for change in (lambda s: s['candidates'][0].update(id='x\n'),
                       lambda s: s['cases'][0]['input'].update(reason='<img src=x onerror=alert(1)>'),
                       lambda s: s['fields'].update(constructor='boolean'),
                       lambda s: s['cases'][0]['input'].update(days=True),
                       lambda s: s['candidates'].append(s['candidates'][0]),
                       lambda s: s.update(labels={})):
            item = copy.deepcopy(spec); change(item); bad.append(json.dumps(item))
        bad += ['{"x":1,"x":2}', '{"__proto__":1}', '{"x":1.0}', '{"x":1e0}',
                '\v{}', '{"x":NaN}', '[' * 20 + '0' + ']' * 20, '{} ' * 90000]
        for text in bad:
            with self.assertRaises(ClarificationError): PolicySession(load_json(text))
        self.assertEqual(self.node({'invalid': bad}), [True] * len(bad))


    def test_max_rule_depth_session_parser_matches_python(self):
        leaf={'field':'x','op':'>','value':0}
        rule=leaf
        for _ in range(6): rule={'or':[rule,leaf]}
        spec={'schema':'executable-clarifications/policy-v1','fields':{'x':'integer'},
              'candidates':[{'id':'a','rule':rule},{'id':'b','rule':leaf}],
              'cases':[{'id':'one','input':{'x':1}}]}
        actual=self.node({'roundtrip':spec})
        self.assertEqual(actual['record'], PolicySession(spec).export_record())
        self.assertLessEqual(actual['bytes'],262144)
