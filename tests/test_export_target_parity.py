"""Browser targets obey the same bounded grammar as Python export, without import."""
import json
import keyword
import subprocess
import unittest
from pathlib import Path

from executable_clarifications.core import ClarificationError
from executable_clarifications.examples import ExampleSet
from executable_clarifications.session import contract_template, render_contract

ROOT = Path(__file__).resolve().parents[1]
SPEC = {'schema': 'executable-clarifications/example-set-v1', 'fields': {'age': 'integer'},
        'examples': [{'id': 'boundary', 'input': {'age': 30}, 'expected': True}]}


class ExportTargetParityTests(unittest.TestCase):
    def compare_targets(self, targets):
        session = ExampleSet(SPEC)
        session.confirm()
        program = """const E=require(process.argv[1]); let raw='';process.stdin.on('data',x=>raw+=x);
process.stdin.on('end',async()=>{const p=JSON.parse(raw),s=await E.create(p.spec);s.confirm();
console.log(JSON.stringify(p.targets.map(t=>{try{return {ok:true,contract:s.contract(t,p.template)};}
catch(e){return {ok:false};}})));});"""
        result = subprocess.run(['node', '-e', program, str(ROOT/'web/example-engine.js')],
                                input=json.dumps({'spec': SPEC, 'targets': targets,
                                                  'template': contract_template()}),
                                text=True, capture_output=True, timeout=10, check=True)
        actual = json.loads(result.stdout)
        for target, observed in zip(targets, actual, strict=True):
            try:
                expected = {'ok': True, 'contract': render_contract(session, target)}
            except ClarificationError:
                expected = {'ok': False}
            with self.subTest(target=target):
                self.assertEqual(observed, expected)

    def test_reviewed_module_and_function_names_match_python_bytes(self):
        self.compare_targets(['implementation:decide', 'access.rules:allow', '_pkg._rule:_check',
                              'match.case:type', 'a:b', 'x'*254 + ':f', '__proto__:constructor'])

    def test_invalid_types_keywords_whitespace_and_paths_are_refused(self):
        targets = [None, 7, True, [], {}, '', 'a', ':b', 'a:', 'a:b:c', 'a..b:f',
                   '.a:f', 'a.:f', 'a:b.c', 'a/b:f', 'a:b()', 'a:f\n', ' a:f',
                   'a:f ', 'a:f\r', 'a:f\x00', 'é:f', 'a:K', 'x'*255 + ':f']
        targets.extend(word+':f' for word in keyword.kwlist)
        targets.extend('a:'+word for word in keyword.kwlist)
        self.compare_targets(targets)

    def test_target_choice_never_confirms_examples(self):
        program = """const E=require(process.argv[1]);(async()=>{const s=await E.create(JSON.parse(process.argv[2]));
let refused=false;try{s.contract('billing.policy:eligible','__DATA__')}catch(e){refused=true}
console.log(JSON.stringify({refused,status:s.status(),record:s.record()}));})();"""
        result = subprocess.run(['node', '-e', program, str(ROOT/'web/example-engine.js'), json.dumps(SPEC)],
                                capture_output=True, text=True, timeout=10, check=True)
        observed = json.loads(result.stdout)
        self.assertTrue(observed['refused'])
        self.assertEqual(observed['status'], 'PENDING_REVIEW')
        self.assertFalse(observed['record']['confirmed'])
        self.assertNotIn('target', observed['record'])
