"""Bounded pure-expression clarifications. Do not execute generated Python."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class ClarificationError(ValueError):
    pass


OPERATORS = {'<','<=','>','>=','==','!='}


@dataclass(frozen=True)
class Candidate:
    id: str
    field: str
    operator: str
    threshold: int

    def __post_init__(self):
        if (not self.id or not self.field or not self.field.isidentifier() or
                self.operator not in OPERATORS or type(self.threshold) is not int):
            raise ClarificationError('candidate must have id, safe field, operator and integer threshold')

    def evaluate(self, example: dict[str, Any]) -> bool | None:
        if self.field not in example:
            return None  # Missing data is not a false answer.
        value=example[self.field]
        if type(value) is not int:
            return None  # An unknown or invalid type needs human input.
        return {'<':lambda:a_lt(value,self.threshold),
                '<=':lambda:value<=self.threshold,
                '>':lambda:value>self.threshold,
                '>=':lambda:value>=self.threshold,
                '==':lambda:value==self.threshold,
                '!=':lambda:value!=self.threshold}[self.operator]()


def a_lt(a:int,b:int)->bool:
    return a<b


def find_distinguishing(candidates:list[Candidate], domain:list[int]) -> dict[str,Any] | None:
    if len(candidates)<2 or len({c.id for c in candidates})!=len(candidates):
        raise ClarificationError('need at least two uniquely named candidates')
    if len({c.field for c in candidates})!=1:
        raise ClarificationError('first edition supports one field only')
    if not domain or len(domain)>1000 or any(type(i) is not int for i in domain):
        raise ClarificationError('domain must contain up to 1000 bounded integers')
    best=None
    for x in sorted(set(domain)):
        example={candidates[0].field:x}
        result={c.id:c.evaluate(example) for c in candidates}
        distinct=len(set(result.values()))
        if distinct<2:continue
        # More separated candidate groups then closest to authored threshold,
        # not an unjustified claim of optimal information gain.
        score=(-distinct, min(abs(x-c.threshold) for c in candidates),abs(x),x)
        if best is None or score<best[0]:
            best=(score,{'input':example,'outputs':result,'status':'BEHAVIORAL_DISAGREEMENT'})
    return best[1] if best else None


def default_boundary_domain(candidates:list[Candidate]) -> list[int]:
    return sorted({v for c in candidates for v in (c.threshold-1,c.threshold,c.threshold+1)})


def choose(candidates:list[Candidate], case:dict[str,Any], selected_id:str) -> dict[str,Any]:
    """A human choice creates an example-scoped executable expectation."""
    valid_ids={c.id for c in candidates}
    if selected_id not in valid_ids | {'neither'}:
        raise ClarificationError('unknown choice')
    if case is None or case.get('status')!='BEHAVIORAL_DISAGREEMENT':
        raise ClarificationError('no discriminating case')
    if set(case.get('outputs',{}))!=valid_ids:
        raise ClarificationError('case/candidate mismatch')
    if selected_id=='neither':
        return {'status':'UNRESOLVED','selected':'neither','example':case['input'],
                'expected':None,'scope':'example-only'}
    candidate=next(c for c in candidates if c.id==selected_id)
    expected=candidate.evaluate(case['input'])
    if type(expected) is not bool or case['outputs'][selected_id]!=expected:
        raise ClarificationError('case does not match selected executable predicate')
    return {'status':'RECORDED_CHOICE','selected':selected_id,'example':case['input'],
            'expected':expected,'scope':'example-only', 'candidate':{'id':candidate.id,
                'field':candidate.field,'operator':candidate.operator,'threshold':candidate.threshold}}


def render_test(record:dict[str,Any]) -> str:
    """Generate runnable stdlib unittest for a human-chosen DSL expression.

    Input JSON is string-literal encoded, never interpolated into executable code.
    """
    if record.get('status')!='RECORDED_CHOICE' or type(record.get('expected')) is not bool:
        raise ClarificationError('unresolved choice cannot generate passing test')
    candidate=record['candidate']
    obj={'id':candidate['id'],'field':candidate['field'],
         'operator':candidate['operator'],'threshold':candidate['threshold']}
    # Validate the record before using it; no generated arbitrary code.
    valid=Candidate(**obj)
    if valid.evaluate(record['example'])!=record['expected']:
        raise ClarificationError('chosen example no longer matches candidate')
    record_bytes=json.dumps({'candidate':obj,'example':record['example'],'expected':record['expected']},
                            sort_keys=True, separators=(',',':'))
    return ('''"""Generated from a human-selected example; does not prove full specification."""\n'''
            '''import json\nimport unittest\nfrom executable_clarifications.core import Candidate\n\n'''
            'DATA = json.loads('+repr(record_bytes)+')\n\n'
            '''class RecordedDecision(unittest.TestCase):\n'''
            '''    def test_selected_boundary_case(self):\n'''
            '''        candidate = Candidate(**DATA['candidate'])\n'''
            '''        self.assertEqual(candidate.evaluate(DATA['example']), DATA['expected'])\n'''
            '''\nif __name__ == '__main__': unittest.main()\n''')
