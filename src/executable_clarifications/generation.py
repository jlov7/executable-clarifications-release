"""Expand reviewed JSON integer templates, without interpreting prose or code."""
from __future__ import annotations

import re

from .core import OPERATORS, Candidate, ClarificationError
from .session import SAFE_INTEGER

SCHEMA = 'executable-clarifications/integer-grid-v1'


def generate_candidates(spec: dict) -> list[Candidate]:
    """Generate 2..64 predicates from one field, operators and integer thresholds.

    Only this fixed comparison template is supported. Source requirements and
    intended labels are not generator inputs. A schema tag does not certify who
    reviewed a specification or whether its candidates cover the intended rule.
    """
    if (type(spec) is not dict or set(spec) != {'schema', 'field', 'operators', 'thresholds'}
            or spec['schema'] != SCHEMA):
        raise ClarificationError('invalid reviewed integer-grid specification')
    field, operators, thresholds = spec['field'], spec['operators'], spec['thresholds']
    if (type(field) is not str
            or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', field) is None):
        raise ClarificationError('field requires a portable identifier')
    if (type(operators) is not list or not 1 <= len(operators) <= len(OPERATORS)
            or any(type(op) is not str or op not in OPERATORS for op in operators)
            or len(set(operators)) != len(operators)):
        raise ClarificationError('operators require unique allowlisted comparisons')
    if (type(thresholds) is not list or not 1 <= len(thresholds) <= 64
            or any(type(t) is not int or abs(t) > SAFE_INTEGER for t in thresholds)
            or len(set(thresholds)) != len(thresholds)):
        raise ClarificationError('thresholds require unique portable integers')
    if not 2 <= len(operators) * len(thresholds) <= 64:
        raise ClarificationError('reviewed grid must generate 2..64 candidates')
    pairs = [(op, threshold) for op in sorted(operators) for threshold in sorted(thresholds)]
    return [Candidate(f'c{i}', field, op, threshold) for i, (op, threshold) in enumerate(pairs)]
