import copy
import importlib.util
import unittest

from executable_clarifications.core import ClarificationError
from executable_clarifications.session import Session


class ReviewedGeneration(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('executable_clarifications.generation'),
                             'Missing reviewed JSON integer-predicate generator')
        from executable_clarifications.generation import generate_candidates
        self.generate = generate_candidates
        self.spec = {'schema': 'executable-clarifications/integer-grid-v1',
                     'field': 'days', 'operators': ['<=', '<'], 'thresholds': [30, 20]}

    def test_reviewed_grid_generates_distinct_executable_predicates(self):
        candidates = self.generate(self.spec)
        self.assertEqual([(c.id, c.field, c.operator, c.threshold) for c in candidates],
                         [('c0', 'days', '<', 20), ('c1', 'days', '<', 30),
                          ('c2', 'days', '<=', 20), ('c3', 'days', '<=', 30)])
        self.assertEqual([c.evaluate({'days': 30}) for c in candidates],
                         [False, False, False, True])

    def test_input_order_does_not_change_session_identity(self):
        other = copy.deepcopy(self.spec)
        other['operators'].reverse(); other['thresholds'].reverse()
        first = Session(self.generate(self.spec), [19, 20, 21, 29, 30, 31])
        second = Session(self.generate(other), [19, 20, 21, 29, 30, 31])
        self.assertEqual(first.export_record(), second.export_record())
        self.assertEqual(first.question()['input'], {'days': 21})

    def test_only_declared_schema_fields_are_accepted(self):
        for extra in ['requirement', 'intended_labels', 'code']:
            bad = dict(self.spec, **{extra: 'not a predicate input'})
            with self.subTest(extra=extra), self.assertRaises(ClarificationError):
                self.generate(bad)
        for bad in [None, [], {}, dict(self.spec, schema='unrecognized')]:
            with self.subTest(bad=bad), self.assertRaises(ClarificationError):
                self.generate(bad)

    def test_unsafe_fields_and_operators_fail_closed(self):
        for field in ['', 'a.b', 'a-b', '__import__("os")', 5, 'x' * 65]:
            with self.subTest(field=field), self.assertRaises(ClarificationError):
                self.generate(dict(self.spec, field=field))
        for operators in [[], ['exec'], ['<', '<'], '<', [None], [True], ['<'] * 65]:
            with self.subTest(operators=operators), self.assertRaises(ClarificationError):
                self.generate(dict(self.spec, operators=operators))

    def test_thresholds_require_unique_portable_integers(self):
        for thresholds in [[], [True], [30.0], ['30'], [None], [2**53],
                           [-(2**53)], [30, 30], range(2), [{}]]:
            with self.subTest(thresholds=thresholds), self.assertRaises(ClarificationError):
                self.generate(dict(self.spec, thresholds=thresholds))
        portable = self.generate(dict(self.spec, operators=['=='],
                                      thresholds=[-(2**53 - 1), 2**53 - 1]))
        self.assertIs(portable[0].evaluate({'days': -(2**53 - 1)}), True)
        self.assertIs(portable[1].evaluate({'days': 2**53 - 1}), True)

    def test_candidate_count_is_bounded_before_expansion(self):
        for spec in [dict(self.spec, operators=['<'], thresholds=[30]),
                     dict(self.spec, operators=['<'], thresholds=list(range(65)))]:
            with self.subTest(spec=spec), self.assertRaises(ClarificationError):
                self.generate(spec)
        self.assertEqual(len(self.generate(dict(self.spec, operators=['<'],
                                               thresholds=list(range(64))))), 64)

    def test_unsupported_input_values_remain_unknown(self):
        candidate = self.generate(self.spec)[0]
        for example in [{}, {'days': None}, {'days': True}, {'days': 20.0},
                        {'days': '20'}, {'days': []}, {'days': {}}]:
            with self.subTest(example=example):
                self.assertIsNone(candidate.evaluate(example))
        for domain in [[None], [True], [20.0], ['20'], [2**53], []]:
            with self.subTest(domain=domain), self.assertRaises(ClarificationError):
                Session(self.generate(self.spec), domain)

    def test_neither_stays_unresolved_with_generated_candidates(self):
        from executable_clarifications.session import render_contract
        session = Session(self.generate(self.spec), [19, 20, 21, 29, 30, 31])
        session.answer(session.question()['id'], None)
        self.assertEqual(session.status, 'UNRESOLVED')
        with self.assertRaises(ClarificationError):
            render_contract(session, 'implementation:decide')
