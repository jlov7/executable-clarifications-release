"""Read-only policy impact on a bounded, disclosed finite input grid."""
from itertools import product

from .policy import evaluate, fail, validate_policy
from .session import SAFE_INTEGER, canonical

INPUT_LIMIT = 4096
ATTEMPT_LIMIT = 5120
DOMAIN_VALUE_LIMIT = 1024
WITNESS_LIMIT = 128
REPORT_BYTE_LIMIT = 1048576


def compare_policies(baseline, proposed, observed_case_ids=()):
    """Compare aligned candidate IDs, without inferring intended outputs.

    Observed IDs refer only to baseline cases already explicitly answered by an
    operator. They classify changed inputs; their labels are never transferred.
    """
    baseline, proposed = validate_policy(baseline), validate_policy(proposed)
    cases = {c['id']: c['input'] for c in baseline['cases']}
    if (type(observed_case_ids) not in (list, tuple) or len(observed_case_ids) > 256 or
            any(type(x) is not str or x not in cases for x in observed_case_ids) or
            len(set(observed_case_ids)) != len(observed_case_ids)):
        fail('observed case IDs must be distinct known baseline cases')
    observed = {canonical(cases[x]) for x in observed_case_ids}
    old = {c['id']: c['rule'] for c in baseline['candidates']}
    new = {c['id']: c['rule'] for c in proposed['candidates']}
    fields = sorted(baseline['fields'].keys() | proposed['fields'].keys())
    def vocabulary(kind):
        return {'enum': sorted(kind['enum'])} if type(kind) is dict else kind
    incompatible = [{'field': f, 'baseline': baseline['fields'].get(f),
                     'proposed': proposed['fields'].get(f)} for f in fields
                    if vocabulary(baseline['fields'].get(f)) != vocabulary(proposed['fields'].get(f))]
    report = {'schema': 'executable-clarifications/policy-impact-v1',
              'compatible': not incompatible, 'incompatible_fields': incompatible,
              'added_candidates': sorted(new.keys() - old.keys()),
              'removed_candidates': sorted(old.keys() - new.keys()),
              'candidate_impacts': [], 'coverage': None, 'witnesses': [],
              'output': {'witness_limit': WITNESS_LIMIT, 'report_byte_limit': REPORT_BYTE_LIMIT,
                         'sampling': 'first input per candidate, direction and observed status',
                         'omitted_change_pairs': 0, 'truncated': False, 'stop_reason': None},
              'scope': 'checked finite inputs only; outputs are not labels, intent or universal semantic equivalence'}
    def finish():
        report['output']['report_bytes'] = 0
        for _ in range(4):
            report['output']['report_bytes'] = len(canonical(report).encode())
        if report['output']['report_bytes'] > REPORT_BYTE_LIMIT: fail('comparison report exceeds byte limit')
        return report
    if incompatible: return finish()
    seeds = [c['input'] for spec in (baseline, proposed) for c in spec['cases']]
    values = {f: set() for f in fields}
    references = []
    def collect(node, referenced):
        if 'and' in node or 'or' in node:
            for child in node.get('and', node.get('or')): collect(child, referenced)
        else:
            referenced.add(node['field'])
            if baseline['fields'][node['field']] == 'integer':
                values[node['field']].update(node['value'] if node['op'] == 'in' else [node['value']])
    for spec in (baseline, proposed):
        referenced = set()
        for candidate in spec['candidates']: collect(candidate['rule'], referenced)
        references.append(referenced)
    sizes = {}
    for f in fields:
        kind = baseline['fields'][f]
        if kind == 'integer':
            supplied = {x[f] for x in seeds}
            anchors = values[f] | supplied
            eligible = {n + offset for n in anchors for offset in (-1, 0, 1)
                        if abs(n + offset) <= SAFE_INTEGER}
            # All supplied values survive the cap (at most 512 per field).
            retained = supplied | set(sorted(eligible - supplied)[:DOMAIN_VALUE_LIMIT - len(supplied)])
            values[f] = sorted(retained)
            count = len(eligible)
        else:
            values[f] = [False, True] if kind == 'boolean' else sorted(kind['enum'])
            count = len(values[f])
        sizes[f] = {'eligible_values': count, 'retained_values': len(values[f]),
                    'omitted_values': count - len(values[f])}
    total = 1
    for f in fields: total *= len(values[f])
    coverage = {'method': 'supplied-inputs-then-finite-cartesian-grid',
                'input_limit': INPUT_LIMIT, 'domain_value_limit': DOMAIN_VALUE_LIMIT,
                'attempt_limit': ATTEMPT_LIMIT, 'attempts': 0,
                'domains': values, 'domain_sizes': sizes,
                'baseline_unreferenced_fields': sorted(set(fields) - references[0]),
                'proposed_unreferenced_fields': sorted(set(fields) - references[1]),
                'unreferenced_fields': sorted(set(fields) - references[0] - references[1]),
                'total_combinations': str(total), 'checked_combinations': '0',
                'omitted_combinations': str(total), 'finite_domain_complete': False,
                'domain_complete': not any(s['omitted_values'] for s in sizes.values()),
                'truncated': False, 'stop_reasons': []}
    report['coverage'] = coverage
    impacts = report['candidate_impacts']
    for identity in sorted(old.keys() & new.keys()):
        impacts.append({'candidate_id': identity, 'status': 'unchanged-on-checked-inputs',
                        'false_to_true_count': 0, 'true_to_false_count': 0,
                        'observed_false_to_true_count': 0, 'observed_true_to_false_count': 0,
                        'unobserved_false_to_true_count': 0, 'unobserved_true_to_false_count': 0})
    def inputs():
        yield from seeds
        for row in product(*(values[f] for f in fields)): yield dict(zip(fields, row))
    seen, samples = set(), {}
    for example in inputs():
        if coverage['attempts'] == ATTEMPT_LIMIT: break
        coverage['attempts'] += 1
        key = canonical(example)
        if key in seen: continue
        if len(seen) == INPUT_LIMIT: break
        seen.add(key)
        exercised = key in observed
        for item in impacts:
            identity = item['candidate_id']
            before, after = evaluate(old[identity], example), evaluate(new[identity], example)
            if before == after: continue
            direction = 'true_to_false' if before else 'false_to_true'
            item['status'] = 'changed-on-checked-inputs'
            item[direction + '_count'] += 1
            item[('observed_' if exercised else 'unobserved_') + direction + '_count'] += 1
            sample_key = (identity, direction, exercised)
            if sample_key not in samples:
                samples[sample_key] = {'candidate_id': identity, 'input': dict(example),
                                       'before': before, 'after': after,
                                       'exercised_by_observed_example': exercised}
    coverage['checked_combinations'] = str(len(seen))
    coverage['omitted_combinations'] = str(total - len(seen))
    coverage['finite_domain_complete'] = len(seen) == total
    if not coverage['domain_complete']: coverage['stop_reasons'].append('domain-value-limit')
    if len(seen) < total:
        coverage['stop_reasons'].append('attempt-limit' if coverage['attempts'] == ATTEMPT_LIMIT else 'input-limit')
    coverage['truncated'] = bool(coverage['stop_reasons'])
    changes = sum(x['false_to_true_count'] + x['true_to_false_count'] for x in impacts)
    output = report['output']
    output['omitted_change_pairs'] = changes
    for sample in samples.values():
        if len(report['witnesses']) == WITNESS_LIMIT:
            output['stop_reason'] = 'witness-limit'; break
        report['witnesses'].append(sample)
        output['omitted_change_pairs'] -= 1
        if len(canonical(report).encode()) > REPORT_BYTE_LIMIT - 128:
            report['witnesses'].pop(); output['omitted_change_pairs'] += 1
            output['stop_reason'] = 'report-byte-limit'; break
    output['truncated'] = output['omitted_change_pairs'] > 0
    if output['truncated'] and output['stop_reason'] is None:
        output['stop_reason'] = 'representative-samples'
    return finish()
