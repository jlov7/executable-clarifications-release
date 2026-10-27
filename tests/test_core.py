import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from executable_clarifications.core import (
    Candidate,
    ClarificationError,
    choose,
    default_boundary_domain,
    find_distinguishing,
    render_test,
)

C=[Candidate('inclusive','age_days','<=',30),Candidate('exclusive','age_days','<',30)]


class ClarificationTests(unittest.TestCase):
    def case(self):return find_distinguishing(C,default_boundary_domain(C))
    def test_exact_boundary_selected(self):
        self.assertEqual(self.case()['input'],{'age_days':30})

    def test_outputs_opposite(self):
        self.assertEqual(self.case()['outputs'],{'inclusive':True,'exclusive':False})

    def test_out_of_domain_returns_none(self):
        self.assertIsNone(find_distinguishing(C,[1,2,3]))

    def test_choose_inclusive(self):
        self.assertIs(choose(C,self.case(),'inclusive')['expected'],True)

    def test_choose_exclusive(self):
        self.assertIs(choose(C,self.case(),'exclusive')['expected'],False)

    def test_neither_unresolved(self):
        r=choose(C,self.case(),'neither')
        self.assertEqual(r['status'],'UNRESOLVED')
        with self.assertRaises(ClarificationError):render_test(r)

    def test_choice_scope_is_one_example(self):
        self.assertEqual(choose(C,self.case(),'inclusive')['scope'],'example-only')

    def test_unknown_choice_fails(self):
        with self.assertRaises(ClarificationError):choose(C,self.case(),'bogus')

    def test_candidate_id_unique(self):
        with self.assertRaises(ClarificationError):find_distinguishing([C[0],C[0]],[30])

    def test_missing_input_unknown(self):
        self.assertIsNone(C[0].evaluate({}))

    def test_none_input_unknown(self):
        self.assertIsNone(C[0].evaluate({'age_days':None}))

    def test_float_input_unknown(self):
        self.assertIsNone(C[0].evaluate({'age_days':30.0}))

    def test_bool_input_unknown(self):
        self.assertIsNone(C[0].evaluate({'age_days':True}))

    def test_candidate_unsafe_expression_refused(self):
        with self.assertRaises(ClarificationError):Candidate('id','age_days','exec',30)

    def test_multi_field_out_of_scope(self):
        with self.assertRaises(ClarificationError):find_distinguishing([C[0],Candidate('other','price','<',10)],[30])

    def test_invalid_domain_refused(self):
        with self.assertRaises(ClarificationError):find_distinguishing(C,[30.0])

    def test_export_executes_actual_selected_boundary(self):
        r=choose(C,self.case(),'exclusive')
        code=render_test(r)
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'test_choice.py';target.write_text(code)
            result=subprocess.run([sys.executable,str(target)],text=True,capture_output=True, check=False)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_tampered_decision_rejected(self):
        r=choose(C,self.case(),'inclusive');r['expected']=False
        with self.assertRaises(ClarificationError):render_test(r)

    def test_domain_is_deterministic(self):
        self.assertEqual(default_boundary_domain(C),[29,30,31])

    def test_web_ui_has_no_network_calls(self):
        files=(Path(__file__).parents[1]/'web')
        js=(files/'app.js').read_text()
        self.assertNotIn('fetch(',js)
        self.assertIn('UNRESOLVED',js)
        self.assertIn('age_days:30',js)


if __name__=='__main__':unittest.main()
