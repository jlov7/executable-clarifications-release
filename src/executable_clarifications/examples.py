"""Supplied typed truth tables, independent of candidate generation and sessions."""
import re

from .policy import evaluate, fail, identifier, keys, load_json, validate_policy
from .session import SAFE_INTEGER, canonical, digest

SCHEMA = 'executable-clarifications/example-set-v1'
REVIEW_SCHEMA = 'executable-clarifications/example-review-v1'
SCOPE = 'supplied-examples-only'


def validate_examples(spec):
    try: spec = load_json(canonical(spec))
    except (ValueError, TypeError, RecursionError): fail('example set must be bounded JSON')
    if len(canonical(spec).encode('utf-8')) > 131072: fail('example set exceeds 131072 bytes')
    keys(spec, ('schema', 'fields', 'examples'))
    if spec['schema'] != SCHEMA: fail('unsupported example set schema')
    fields = spec['fields']
    if type(fields) is not dict or not 1 <= len(fields) <= 16: fail('provide 1..16 fields')
    for name, kind in fields.items():
        identifier(name)
        if kind in ('integer', 'boolean'): continue
        keys(kind, ('enum',))
        values = kind['enum']
        if (type(values) is not list or not 1 <= len(values) <= 32 or
                any(type(v) is not str or re.fullmatch(r'[A-Za-z0-9 _.-]{1,64}', v) is None
                    for v in values) or len(set(values)) != len(values)):
            fail('enum requires 1..32 unique plain text values')
    rows = spec['examples']
    if type(rows) is not list or not 1 <= len(rows) <= 256: fail('provide 1..256 examples')
    ids, inputs = set(), set()
    for row in rows:
        keys(row, ('id', 'input', 'expected')); identifier(row['id'])
        if row['id'] in ids: fail('duplicate example identity')
        ids.add(row['id']); keys(row['input'], fields)
        for name, value in row['input'].items():
            kind = fields[name]
            valid = (type(value) is int and abs(value) <= SAFE_INTEGER if kind == 'integer'
                     else type(value) is bool if kind == 'boolean'
                     else type(value) is str and value in kind['enum'])
            if not valid: fail('value does not match its declared field type')
        if type(row['expected']) is not bool: fail('expected must be boolean')
        key = canonical(row['input'])
        if key in inputs: fail('duplicate or contradictory example input')
        inputs.add(key)
    return spec


class ExampleSet:
    def __init__(self, spec):
        self._spec = validate_examples(spec)
        self._version = digest(self._spec)
        self._confirmed = False

    @property
    def status(self): return 'REVIEWED_EXAMPLES' if self._confirmed else 'PENDING_REVIEW'

    def confirm(self):
        """Explicit operator confirmation of every supplied input and expected boolean."""
        self._confirmed = True

    def examples(self):
        if not self._confirmed: return []
        return [{'input': dict(row['input']), 'expected': row['expected'], 'question_id': row['id']}
                for row in self._spec['examples']]

    def export_record(self):
        return load_json(canonical({'schema': REVIEW_SCHEMA, 'example_set': self._spec,
                                   'version_digest': self._version, 'confirmed': self._confirmed,
                                   'scope': SCOPE}))

    @classmethod
    def from_record(cls, record):
        try: record = load_json(canonical(record))
        except (ValueError, TypeError, RecursionError): fail('review must be bounded JSON')
        keys(record, ('schema', 'example_set', 'version_digest', 'confirmed', 'scope'))
        if (record['schema'] != REVIEW_SCHEMA or record['scope'] != SCOPE or
                type(record['confirmed']) is not bool): fail('invalid example review record')
        result = cls(record['example_set'])
        if result._version != record['version_digest']: fail('example set digest mismatch')
        if record['confirmed']: result.confirm()
        return result

    def audit(self, policy):
        """Read-only declared-rule diagnostics. Never run implementation code."""
        if not self._confirmed: fail('confirm the supplied examples before candidate audit')
        policy = validate_policy(policy)
        if canonical(policy['fields']) != canonical(self._spec['fields']):
            fail('candidate audit requires the exact declared field vocabulary')
        matrix = [{'id': row['id'], 'input': dict(row['input']), 'expected': row['expected'],
                   'predictions': {c['id']: evaluate(c['rule'], row['input'])
                                   for c in policy['candidates']}}
                  for row in self._spec['examples']]
        candidates = [{'candidate_id': c['id'], 'mismatch_ids': [row['id'] for row in matrix
                       if row['predictions'][c['id']] is not row['expected']]}
                      for c in policy['candidates']]
        fitting = [c['candidate_id'] for c in candidates if not c['mismatch_ids']]
        return {'status': 'CANDIDATE_FIT' if fitting else 'NO_CANDIDATE_MATCH',
                'fitting_candidates': fitting, 'candidates': candidates, 'matrix': matrix,
                'example_digest': self._version, 'policy_digest': digest(policy),
                'scope': 'supplied examples only; no completeness or authenticity proof'}
