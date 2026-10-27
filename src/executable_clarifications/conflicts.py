"""Explain a finite candidate mismatch without claiming to infer or correct intent."""
from .examples import ExampleSet


def explain_conflict(examples: ExampleSet, policy: dict) -> dict:
    """Return a deterministic deletion-minimal subset of confirmed examples.

    Removing any retained example admits at least one offered candidate. This
    does not guarantee the smallest possible subset, that the labels are wrong,
    that the candidate set is complete, or that human intent is ambiguous.
    Predicates are evaluated by the existing bounded, non-executing policy DSL.
    """
    audit = examples.audit(policy)
    rows = sorted(audit['matrix'], key=lambda row: row['id'])
    candidates = sorted(item['candidate_id'] for item in audit['candidates'])

    def fits(subset):
        return [candidate for candidate in candidates if all(
            row['predictions'][candidate] is row['expected'] for row in subset)]

    fitting = fits(rows)
    result = {'schema': 'executable-clarifications/conflict-explanation-v1',
              'status': 'OFFERED_CANDIDATE_FITS' if fitting else 'NO_OFFERED_CANDIDATE_FITS',
              'example_digest': audit['example_digest'], 'policy_digest': audit['policy_digest'],
              'fitting_candidates': fitting, 'core_example_ids': [],
              'candidate_eliminations': [], 'removal_witnesses': [],
              'minimum_cardinality_claimed': False, 'labels_judged_incorrect': False,
              'scope': 'Deletion-minimal mismatch within the offered candidates and confirmed examples; '
                       'not inferred intent, a complete specification or a diagnosis of incorrect labels.'}
    if fitting:
        return result
    core = list(rows)
    for row in rows:
        remaining = [item for item in core if item['id'] != row['id']]
        if not fits(remaining):
            core = remaining
    result['core_example_ids'] = [row['id'] for row in core]
    result['candidate_eliminations'] = [
        {'candidate_id': candidate, 'mismatched_core_example': next(
            row['id'] for row in core if row['predictions'][candidate] is not row['expected'])}
        for candidate in candidates]
    result['removal_witnesses'] = [
        {'removed_example_id': row['id'], 'fitting_candidate': fits(
            [item for item in core if item['id'] != row['id']])[0]}
        for row in core]
    return result
