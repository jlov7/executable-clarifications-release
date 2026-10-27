"""Example-scoped adaptive clarification over bounded pure predicates.

A balanced split assumes a uniform candidate prior; it is not a calibrated model
of human intent. Generated tests call an explicitly chosen, separately implemented
function. This library never executes that function or generated arbitrary code.
"""
from __future__ import annotations

import hashlib
import json
import keyword
import re
from dataclasses import asdict
from typing import Any

from .core import Candidate, ClarificationError

SCHEMA = 'executable-clarifications/session-v1'
SAFE_INTEGER = 2**53 - 1


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Session:
    def __init__(self, candidates: list[Candidate], domain: list[int]):
        if (type(candidates) is not list or not 2 <= len(candidates) <= 64 or
                any(type(c) is not Candidate for c in candidates)):
            raise ClarificationError('provide 2..64 bounded Candidate objects')
        for c in candidates:
            if (type(c.id) is not str or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}', c.id) is None
                    or type(c.field) is not str
                    or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', c.field) is None
                    or type(c.threshold) is not int or abs(c.threshold) > SAFE_INTEGER):
                raise ClarificationError('candidate exceeds the portable scalar contract')
        if len({c.id for c in candidates}) != len(candidates):
            raise ClarificationError('candidate identities must be unique')
        if len({c.field for c in candidates}) != 1:
            raise ClarificationError('this session supports a single integer field')
        if (type(domain) is not list or not 1 <= len(domain) <= 1000 or
                any(type(x) is not int or abs(x) > SAFE_INTEGER for x in domain)):
            raise ClarificationError('domain requires 1..1000 portable integers')
        self._candidates = tuple(sorted(candidates, key=lambda c: c.id))
        self._remaining = self._candidates
        self._domain = tuple(sorted(set(domain)))
        self._history: list[dict] = []
        self._stopped = False
        self._version = digest(self._spec())

    def _spec(self) -> dict:
        return {'schema': SCHEMA, 'candidates': [asdict(c) for c in self._candidates],
                'domain': list(self._domain)}

    @property
    def remaining_ids(self) -> tuple[str, ...]:
        return tuple(c.id for c in self._remaining)

    @property
    def status(self) -> str:
        if self._stopped:
            return 'UNRESOLVED'
        if len(self._remaining) == 1:
            return 'CANDIDATE_SET_NARROWED'
        return 'OPEN' if self.question() is not None else 'NO_FURTHER_DISAGREEMENT'

    def question(self) -> dict | None:
        if self._stopped or len(self._remaining) < 2:
            return None
        best = None
        for x in self._domain:
            example = {self._candidates[0].field: x}
            outputs = {c.id: c.evaluate(example) for c in self._remaining}
            groups = {str(value).lower(): sorted(k for k, v in outputs.items() if v is value)
                      for value in (False, True)}
            if any(not group for group in groups.values()):
                continue
            score = sum(len(group)**2 for group in groups.values())
            key = (score, abs(x), x)
            if best is None or key < best[0]:
                question = {'input': example, 'outputs': outputs, 'groups': groups,
                            'uniform_expected_remaining': score / len(self._remaining),
                            'remaining_count': len(self._remaining),
                            'scope': 'candidate-disagreement-not-proven-ambiguity'}
                question['id'] = digest({'spec': self._version, 'step': len(self._history),
                                         'input': example, 'outputs': outputs})
                best = (key, question)
        return None if best is None else best[1]

    def answer(self, question_id: str, expected: bool | None) -> None:
        if expected is not None and type(expected) is not bool:
            raise ClarificationError('answer must be a boolean or null for neither')
        question = self.question()
        if question is None or question_id != question['id']:
            raise ClarificationError('stale, unknown, or unavailable question')
        # Use recomputed input/outputs, not values supplied by a client.
        self._history.append({'question_id': question_id, 'expected': expected})
        if expected is None:
            self._stopped = True
        else:
            self._remaining = tuple(c for c in self._remaining
                                    if c.evaluate(question['input']) is expected)

    def export_record(self) -> dict:
        return dict(self._spec(), version_digest=self._version,
                    decisions=[dict(d) for d in self._history], scope='observed-examples-only')

    @classmethod
    def from_record(cls, record: dict) -> Session:
        if (type(record) is not dict or set(record) != {
                'schema', 'candidates', 'domain', 'version_digest', 'decisions', 'scope'}
                or record['schema'] != SCHEMA or record['scope'] != 'observed-examples-only'):
            raise ClarificationError('invalid versioned session record')
        if type(record['candidates']) is not list or len(record['candidates']) > 64:
            raise ClarificationError('invalid candidate collection')
        try:
            candidates = [Candidate(**item) for item in record['candidates']]
        except (TypeError, ValueError, AttributeError) as exc:
            raise ClarificationError('invalid candidate record') from exc
        session = cls(candidates, record['domain'])
        if session._version != record['version_digest']:
            raise ClarificationError('specification version mismatch')
        decisions = record['decisions']
        if type(decisions) is not list or len(decisions) > 64:
            raise ClarificationError('invalid decision history')
        for decision in decisions:
            if type(decision) is not dict or set(decision) != {'question_id', 'expected'}:
                raise ClarificationError('invalid decision record')
            session.answer(decision['question_id'], decision['expected'])
        return session

    def examples(self) -> list[dict]:
        # Re-derive exact question inputs from the initial specification/history.
        replay = Session(list(self._candidates), list(self._domain))
        result = []
        for decision in self._history:
            q = replay.question()
            if decision['expected'] is not None:
                result.append({'input': q['input'], 'expected': decision['expected'],
                               'question_id': decision['question_id']})
            replay.answer(decision['question_id'], decision['expected'])
        return result


def render_contract(session: Session, target: str) -> str:
    """Export tests for a user-owned module:function; never import or run it here."""
    if session.status == 'UNRESOLVED' or not session.examples():
        raise ClarificationError('an unresolved or unanswered session cannot export assertions')
    if type(target) is not str or target.count(':') != 1 or len(target) > 256:
        raise ClarificationError('target must be an explicit module:function')
    module, function = target.split(':')
    parts = module.split('.') + [function]
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', p) or keyword.iskeyword(p) for p in parts):
        raise ClarificationError('target requires plain Python identifiers')
    data = {'module': module, 'function': function, 'examples': session.examples(),
            'specification_digest': session._version, 'session_status': session.status}
    return contract_template().replace('__DATA__', repr(canonical(data)))


def contract_template():
    return ('"""Generated example-scoped contract; not a complete or verified specification.\n'
            'Run only against a reviewed implementation in your own execution environment.\n'
            'Importing a Python module executes its code; this file is not a sandbox.\n"""\n'
            'import importlib\nimport json\nimport unittest\n\n'
            'DATA = json.loads(__DATA__)\n\n'
            'class ImplementationContract(unittest.TestCase):\n'
            '    def test_recorded_examples(self):\n'
            '        module = importlib.import_module(DATA["module"])\n'
            '        implementation = getattr(module, DATA["function"])\n'
            '        self.assertTrue(callable(implementation))\n'
            '        for case in DATA["examples"]:\n'
            '            with self.subTest(question=case["question_id"]):\n'
            '                actual = implementation(dict(case["input"]))\n'
            '                self.assertIs(actual, case["expected"])\n\n'
            'if __name__ == "__main__":\n    unittest.main()\n')


def assumptions(session: Session) -> str:
    return ('# Recorded behavioral assumptions\n\nStatus: ' + session.status +
            '\n\nOnly the chosen inputs are specified. Agreement among candidates is not intent '
            'verification. No identity or authenticity is established by the version digest.\n\n'
            '```json\n' + json.dumps(session.examples(), indent=2) + '\n```\n')


def demo() -> dict:
    candidates = [Candidate(f'c{i}', 'days', '<=', i) for i in (10, 20, 30, 40)]
    session = Session(candidates, list(range(42)))
    first = session.question()
    session.answer(first['id'], True)
    second = session.question()
    session.answer(second['id'], False)
    return {'scope': 'Authored choices for a software demonstration, not human-study data.',
            'questions': [first, second], 'session': session.export_record(),
            'remaining': session.remaining_ids, 'implementation_test': render_contract(
                session, 'implementation:decide'), 'assumptions': assumptions(session)}


if __name__ == '__main__':
    print(json.dumps(demo(), indent=2))
