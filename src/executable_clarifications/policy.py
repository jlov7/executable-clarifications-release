"""Bounded reviewed JSON policies. No code generation, imports, or effects."""
from __future__ import annotations

import json
import re
from operator import eq, ge, gt, le, lt, ne

from .core import ClarificationError
from .session import SAFE_INTEGER, canonical, digest

SCHEMA = 'executable-clarifications/policy-v1'
SESSION_SCHEMA = 'executable-clarifications/policy-session-v1'
REVIEW_SCHEMA = 'executable-clarifications/policy-session-v2'
MAX_BYTES = 262144
FORBIDDEN = {'__proto__', 'prototype', 'constructor'}
OPS = {'==': eq, '!=': ne, '<': lt, '<=': le, '>': gt, '>=': ge}


def fail(message):
    raise ClarificationError(message)


def identifier(value):
    if (type(value) is not str or value in FORBIDDEN or
            re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}', value) is None):
        fail('invalid or unsafe identifier')


def keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        fail('unknown or missing policy fields')


def load_json(content):
    if isinstance(content, bytes):
        try: content = content.decode('utf-8')
        except UnicodeError: fail('JSON must be UTF-8')
    if type(content) is not str or len(content.encode('utf-8')) > MAX_BYTES:
        fail('JSON exceeds 262144 bytes')
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result or k in FORBIDDEN: fail('duplicate or unsafe JSON key')
            result[k] = v
        return result
    def check_depth(value, depth=0):
        if depth > depth_limit: fail(f'JSON nesting exceeds {depth_limit}')
        if isinstance(value, (dict, list)):
            for v in (value.values() if isinstance(value, dict) else value):
                check_depth(v, depth + 1)
    try:
        value = json.loads(content, object_pairs_hook=pairs,
                           parse_constant=lambda _: fail('nonfinite JSON number'),
                           parse_float=lambda _: fail('only integer JSON numbers are supported'))
        depth_limit = 17 if type(value) is dict and value.get('schema') in (SESSION_SCHEMA, REVIEW_SCHEMA) else 16
        check_depth(value)
        return value
    except (ValueError, RecursionError) as exc:
        raise ClarificationError('invalid bounded JSON') from exc


def validate_policy(spec):
    # Copy and enforce the same byte, depth, key and JSON-value boundary for API callers.
    try: spec = load_json(canonical(spec))
    except (ValueError, TypeError, RecursionError) as exc:
        raise ClarificationError('policy must be bounded JSON') from exc
    if len(canonical(spec).encode('utf-8')) > 131072: fail('policy exceeds 131072 bytes')
    keys(spec, ('schema', 'fields', 'candidates', 'cases'))
    if spec['schema'] != SCHEMA: fail('unsupported policy schema')
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
    def scalar(field, value):
        kind = fields[field]
        if kind == 'integer': valid = type(value) is int and abs(value) <= SAFE_INTEGER
        elif kind == 'boolean': valid = type(value) is bool
        else: valid = type(value) is str and value in kind['enum']
        if not valid: fail('value does not match its declared field type')
    def rule(node, depth=0, count=None):
        count = [0] if count is None else count
        count[0] += 1
        if depth > 6 or count[0] > 128: fail('predicate exceeds depth 6 or 128 nodes')
        if type(node) is dict and set(node) in ({'and'}, {'or'}):
            children = next(iter(node.values()))
            if type(children) is not list or not 2 <= len(children) <= 16:
                fail('and/or requires 2..16 predicates')
            for child in children: rule(child, depth + 1, count)
            return
        keys(node, ('field', 'op', 'value'))
        field, op, value = node['field'], node['op'], node['value']
        if type(field) is not str or field not in fields: fail('unknown predicate field')
        if type(op) is not str or op not in (*OPS, 'in'): fail('unsupported comparison')
        if op == 'in':
            if type(value) is not list or not 1 <= len(value) <= 32: fail('in requires 1..32 values')
            for item in value: scalar(field, item)
            if len({canonical(v) for v in value}) != len(value): fail('duplicate membership value')
        else:
            if op not in ('==', '!=') and fields[field] != 'integer':
                fail('ordering comparisons require integer fields')
            scalar(field, value)
    for collection, lower, upper in (('candidates', 2, 32), ('cases', 1, 256)):
        items = spec[collection]
        if type(items) is not list or not lower <= len(items) <= upper:
            fail(f'{collection} requires {lower}..{upper} entries')
        ids = set()
        for item in items:
            keys(item, ('id', 'rule' if collection == 'candidates' else 'input'))
            identifier(item['id'])
            if item['id'] in ids: fail('duplicate identity')
            ids.add(item['id'])
            if collection == 'candidates': rule(item['rule'])
            else:
                keys(item['input'], fields)
                for field, value in item['input'].items(): scalar(field, value)
        items.sort(key=lambda item: item['id'])
    return spec


def evaluate(rule, example):
    if 'and' in rule: return all(evaluate(child, example) for child in rule['and'])
    if 'or' in rule: return any(evaluate(child, example) for child in rule['or'])
    value = example[rule['field']]
    return value in rule['value'] if rule['op'] == 'in' else OPS[rule['op']](value, rule['value'])


def suggest_cases(policy):
    """Enumerate a bounded finite grid. No candidate voting or intent inference."""
    policy = validate_policy(policy)
    fields = sorted(policy['fields'])
    values = {f: set() for f in fields}
    referenced = set()
    def collect(node):
        if 'and' in node or 'or' in node:
            for child in node.get('and', node.get('or')): collect(child)
        else:
            referenced.add(node['field'])
            if policy['fields'][node['field']] == 'integer':
                values[node['field']].update(node['value'] if node['op'] == 'in' else [node['value']])
    for candidate in policy['candidates']: collect(candidate['rule'])
    seeds = list(policy['cases'])
    for field in fields:
        kind = policy['fields'][field]
        if kind == 'boolean': values[field] = [False, True]
        elif kind == 'integer':
            anchors = values[field] | {case['input'][field] for case in seeds}
            values[field] = sorted({n + offset for n in anchors for offset in (-1, 0, 1)
                                    if abs(n + offset) <= SAFE_INTEGER})
        else: values[field] = sorted(kind['enum'])
    added, seen = [], {canonical(c['input']) for c in seeds}
    ids, serial = {c['id'] for c in seeds}, 0
    total = 1
    for field in fields: total *= len(values[field])
    coverage = {'method': 'finite-cartesian-grid' if total <= 4096 else 'seeded-variations-then-grid', 'attempts': 0,
                'attempt_limit': 4096, 'case_limit': 256, 'policy_byte_limit': 131072,
                'truncated': False, 'stop_reason': None,
                'domains': values, 'total_combinations': str(total),
                'unreferenced_fields': sorted(set(fields) - referenced),
                'scope': 'unlabeled finite-domain inputs only; excludes other integers, undeclared fields and intent or exception truth'}
    def grid(index=0, example=None):
        if example is None: example = {}
        if index == len(fields):
            yield dict(example); return
        field = fields[index]
        for value in values[field]:
            example[field] = value
            yield from grid(index + 1, example)
    def variations():
        if total <= 4096:
            yield from grid(); return
        for width in (1, 2):
            for seed in seeds:
                for i, first in enumerate(fields):
                    for a in values[first]:
                        if a == seed['input'][first]: continue
                        if width == 1:
                            yield dict(seed['input'], **{first: a})
                        else:
                            for second in fields[i + 1:]:
                                for b in values[second]:
                                    if b != seed['input'][second]:
                                        yield dict(seed['input'], **{first: a, second: b})
        yield from grid()
    for example in variations():
        if coverage['attempts'] == coverage['attempt_limit']:
            coverage['stop_reason'] = 'attempt-limit'; break
        coverage['attempts'] += 1
        key = canonical(example)
        if key in seen: continue
        if len(policy['cases']) == 256:
            coverage['stop_reason'] = 'case-limit'; break
        while True:
            serial += 1
            identity = f'suggested_{serial:04d}'
            if identity not in ids: break
        case = {'id': identity, 'input': example}
        policy['cases'].append(case)
        if len(canonical(policy).encode('utf-8')) > 131072:
            policy['cases'].pop(); coverage['stop_reason'] = 'policy-byte-limit'; break
        ids.add(identity); seen.add(key); added.append(case)
    coverage['truncated'] = coverage['stop_reason'] is not None
    coverage['covered_combinations'] = str(len(seen))
    coverage['omitted_combinations'] = str(total - len(seen))
    coverage['finite_domain_complete'] = len(seen) == total
    return {'policy': validate_policy(policy), 'added_cases': added, 'coverage': coverage}


class PolicySession:
    def __init__(self, policy):
        self._policy = validate_policy(policy)
        self._version = digest(self._policy)
        self._history = []
        self._actions = None
        self._labels = []
        self._remaining = tuple(c['id'] for c in self._policy['candidates'])
        self._stopped = False
        self._table = {case['id']: {c['id']: evaluate(c['rule'], case['input'])
                                  for c in self._policy['candidates']}
                       for case in self._policy['cases']}

    @property
    def remaining_ids(self): return self._remaining

    def suggest_cases(self): return suggest_cases(self._policy)

    def compare_policy(self, policy):
        from .impact import compare_policies
        observed = [case['id'] for case in self.case_review() if case['observed'] is not None]
        return compare_policies(self._policy, policy, observed)

    @property
    def status(self):
        if self._stopped: return 'UNRESOLVED'
        if not self._remaining: return 'NO_CANDIDATE_MATCH'
        if len(self._remaining) == 1: return 'CANDIDATE_SET_NARROWED'
        return 'OPEN' if self.question() else 'NO_FURTHER_DISAGREEMENT'

    def question(self):
        if self._stopped or len(self._remaining) < 2: return None
        best = None
        for case in self._policy['cases']:
            outputs = {c: self._table[case['id']][c] for c in self._remaining}
            groups = {str(v).lower(): [c for c in self._remaining if outputs[c] is v]
                      for v in (False, True)}
            if any(not g for g in groups.values()): continue
            score = sum(len(g)**2 for g in groups.values())
            key = (score, case['id'])
            if best is None or key < best[0]:
                best = (key, {'id': f'{self._version}:{len(self._history)}:{case["id"]}',
                             'case_id': case['id'], 'input': dict(case['input']), 'outputs': outputs,
                             'groups': groups, 'remaining_count': len(self._remaining),
                             'uniform_expected_remaining': score / len(self._remaining),
                             'scope': 'candidate-disagreement-not-proven-ambiguity'})
        return None if best is None else best[1]

    def answer(self, question_id, expected):
        if expected is not None and type(expected) is not bool: fail('answer must be boolean or null')
        q = self.question()
        if q is None or q['id'] != question_id: fail('stale, unknown, or unavailable question')
        self._history.append({'question_id': question_id, 'expected': expected})
        if self._actions is not None:
            self._actions.append({'kind': 'answer', 'question_id': question_id, 'expected': expected})
        if expected is None: self._stopped = True
        else: self._remaining = tuple(c for c in self._remaining if q['outputs'][c] is expected)

    def undo(self):
        if self._actions is not None:
            if not self._actions: fail('no answer to undo')
            record = self.export_record()
            record['actions'].pop()
            self.__dict__.update(PolicySession.from_record(record).__dict__)
            return
        if not self._history: fail('no answer to undo')
        restored = PolicySession(self._policy)
        for item in self._history[:-1]: restored.answer(item['question_id'], item['expected'])
        self.__dict__.update(restored.__dict__)

    def export_record(self):
        if self._actions is not None:
            return load_json(canonical({'schema': REVIEW_SCHEMA, 'policy': self._policy,
                'version_digest': self._version, 'actions': self._actions,
                'scope': 'observed-examples-only'}))
        return load_json(canonical({'schema': SESSION_SCHEMA, 'policy': self._policy,
            'version_digest': self._version, 'decisions': self._history,
            'scope': 'observed-examples-only'}))

    @classmethod
    def from_record(cls, record):
        if type(record) is dict and record.get('schema') == REVIEW_SCHEMA:
            record = load_json(canonical(record))
            keys(record, ('schema', 'policy', 'version_digest', 'actions', 'scope'))
            if record['scope'] != 'observed-examples-only': fail('unsupported policy session')
            session = cls(record['policy'])
            if session._version != record['version_digest']: fail('policy version mismatch')
            actions = record['actions']
            if type(actions) is not list or len(actions) > 288: fail('invalid review history')
            session._actions = []
            for item in actions:
                if type(item) is not dict: fail('invalid review action')
                if item.get('kind') == 'answer':
                    keys(item, ('kind', 'question_id', 'expected'))
                    session.answer(item['question_id'], item['expected'])
                elif item.get('kind') in ('label', 'reconfirmed'):
                    keys(item, ('kind', 'case_id', 'expected') if item['kind'] == 'label' else
                         ('kind', 'case_id', 'expected', 'source_digest'))
                    if item['kind'] == 'reconfirmed' and type(item['source_digest']) is not str:
                        fail('invalid revision source digest')
                    session.label_case(item['case_id'], item['expected'],
                                       item.get('source_digest'))
                else: fail('invalid review action kind')
            return session
        keys(record, ('schema', 'policy', 'version_digest', 'decisions', 'scope'))
        if record['schema'] != SESSION_SCHEMA or record['scope'] != 'observed-examples-only':
            fail('unsupported policy session')
        session = cls(record['policy'])
        if session._version != record['version_digest']: fail('policy version mismatch')
        decisions = record['decisions']
        if type(decisions) is not list or len(decisions) > 32: fail('invalid decision history')
        for item in decisions:
            keys(item, ('question_id', 'expected'))
            session.answer(item['question_id'], item['expected'])
        return session

    def examples(self):
        if self._actions is not None:
            replay, result = PolicySession(self._policy), []
            replay._actions = []
            for item in self._actions:
                if item['kind'] == 'answer':
                    q = replay.question()
                    if item['expected'] is not None:
                        result.append({'input': q['input'], 'expected': item['expected'],
                                       'question_id': q['id']})
                    replay.answer(item['question_id'], item['expected'])
                else:
                    case = next(c for c in self._policy['cases'] if c['id'] == item['case_id'])
                    result.append({'input': dict(case['input']), 'expected': item['expected'],
                                   'question_id': self._version + ':review:' + case['id']})
                    replay.label_case(item['case_id'], item['expected'], item.get('source_digest'))
            return result
        replay, result = PolicySession(self._policy), []
        for item in self._history:
            q = replay.question()
            if item['expected'] is not None:
                result.append({'input': q['input'], 'expected': item['expected'],
                               'question_id': q['id']})
            replay.answer(item['question_id'], item['expected'])
        return result


    def case_review(self):
        observed = {e['question_id'].rsplit(':', 1)[-1]: e['expected'] for e in self.examples()}
        asked = {d['question_id'].rsplit(':', 1)[-1] for d in self._history}
        return [dict(case, input=dict(case['input']), predictions=dict(self._table[case['id']]),
                     review_status='asked' if case['id'] in asked else
                     'explicitly-labeled' if any(x['case_id'] == case['id'] for x in self._labels)
                     else 'unasked',
                     observed=observed.get(case['id']))
                for case in self._policy['cases']]

    def label_case(self, case_id, expected, source_digest=None):
        if type(expected) is not bool: fail('explicit label must be boolean')
        if type(case_id) is not str or case_id not in self._table: fail('unknown case')
        if (any(x['case_id'] == case_id for x in self._labels) or
                any(d['question_id'].rsplit(':', 1)[-1] == case_id for d in self._history)):
            fail('case already answered; undo before relabeling')
        if source_digest is not None and (type(source_digest) is not str or
                re.fullmatch(r'[0-9a-f]{64}', source_digest) is None or source_digest == self._version):
            fail('invalid revision source digest')
        if self._actions is None:
            self._actions = [dict(kind='answer', **d) for d in self._history]
        if len(self._actions) >= 288: fail('invalid review history')
        action = {'kind': 'label' if source_digest is None else 'reconfirmed',
                  'case_id': case_id, 'expected': expected}
        if source_digest is not None: action['source_digest'] = source_digest
        self._actions.append(action)
        self._labels.append(action)
        self._remaining = tuple(c for c in self._remaining if self._table[case_id][c] is expected)

    def revision_preview(self, policy):
        revised = PolicySession(policy)
        if revised._version == self._version: fail('revision must change the policy')
        def changed(collection):
            old = {x['id']: x for x in self._policy[collection]}
            new = {x['id']: x for x in revised._policy[collection]}
            return sorted(k for k in old.keys() | new.keys() if canonical(old.get(k)) != canonical(new.get(k)))
        pending = []
        for case in self.case_review():
            if case['observed'] is None: continue
            match = next((c for c in revised._policy['cases'] if c['id'] == case['id']), None)
            pending.append({'case_id': case['id'], 'input': case['input'],
                            'expected': case['observed'], 'review_status':
                            'pending-review' if match is not None and canonical(match['input']) == canonical(case['input'])
                            else 'fresh-answer-required'})
        return {'source_digest': self._version,
                'changed_rules': changed('candidates'), 'changed_cases': changed('cases'),
                'fields_changed': canonical(self._policy['fields']) != canonical(revised._policy['fields']),
                'pending': pending, 'impact': self.compare_policy(revised._policy)}

    def reconfirm(self, original_record, case_id):
        original = PolicySession.from_record(original_record)
        preview = original.revision_preview(self._policy)
        item = next((p for p in preview['pending'] if p['case_id'] == case_id), None)
        if item is None or item['review_status'] != 'pending-review':
            fail('changed or unobserved input requires a fresh answer')
        self.label_case(case_id, item['expected'], original._version)
