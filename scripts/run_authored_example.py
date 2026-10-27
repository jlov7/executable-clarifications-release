"""Offline generator -> session -> export using authored regression fixtures.

The answer table is a synthetic test oracle, not independently labeled human data.
This example does not execute the exported test or import its implementation target.
"""
import json
from pathlib import Path

from executable_clarifications.core import ClarificationError
from executable_clarifications.generation import generate_candidates
from executable_clarifications.session import Session, assumptions, render_contract


def run() -> dict:
    fixtures = Path(__file__).resolve().parents[1] / 'tests/fixtures'
    source = json.loads((fixtures / 'reviewed_candidates.json').read_text())['cases']['age_window']
    candidates = generate_candidates(source['generator_input'])
    session = Session(candidates, source['domain'])
    labels = json.loads((fixtures / 'intended_behavior.json').read_text())['cases']['age_window']
    for _ in range(64):
        question = session.question()
        if question is None:
            break
        label = next(row for row in labels if row['input'] == question['input'])
        session.answer(question['id'], label['expected'])
    else:
        raise ClarificationError('authored example exceeded its question limit')
    return {'provenance': 'authored regression fixtures, not human evidence',
            'candidate_count': len(candidates), 'session': session.export_record(),
            'implementation_test': render_contract(session, 'implementation:decide'),
            'assumptions': assumptions(session)}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
