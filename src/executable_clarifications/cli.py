"""Record bounded example answers and export, but never execute, a contract."""
import argparse
import json
import os
import stat
from importlib.resources import files
from pathlib import Path

from . import __version__
from ._output import write_outputs
from .conflicts import explain_conflict
from .core import ClarificationError
from .examples import REVIEW_SCHEMA as EXAMPLE_REVIEW_SCHEMA
from .examples import ExampleSet
from .generation import generate_candidates
from .policy import MAX_BYTES, REVIEW_SCHEMA, SESSION_SCHEMA, PolicySession, load_json
from .session import Session, canonical, render_contract


def _read_input(path, limit):
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(descriptor, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ClarificationError('input must be a regular file')
            return stream.read(limit + 1)
    except OSError as exc:
        raise ClarificationError('input must be a readable regular file') from exc


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ClarificationError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=__version__)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument('--policy', type=Path, help='reviewed multi-field policy-v1 JSON')
    source_group.add_argument('--examples', type=Path, help='independent typed example-set-v1 JSON')
    parser.add_argument('--confirm-examples', action='store_true', help='explicitly confirm every supplied example')
    parser.add_argument('--audit-policy', type=Path, help='read-only reviewed candidate mismatch audit')
    parser.add_argument('--explain-conflict', action='store_true',
                        help='show a deletion-minimal confirmed-example mismatch; requires --audit-policy')
    source_group.add_argument('--resume', type=Path, help='validated local session JSON')
    parser.add_argument('--save-session', type=Path, help='save a new session file; never overwrite')
    parser.add_argument('--undo', action='store_true', help='undo the last custom-policy answer')
    parser.add_argument('--suggest-cases', action='store_true', help='preview unlabeled boundary/exception inputs')
    parser.add_argument('--compare-policy', type=Path, help='read-only finite semantic impact of a proposed policy')
    parser.add_argument('--export-policy', type=Path, help='write suggested policy to a new file, without answers')
    parser.add_argument('--label-case', action='append', default=[], metavar='ID=true|false',
                        help='explicitly label a custom case; repeat in review order after adaptive answers')
    source_group.add_argument('--grid', type=Path, help='reviewed JSON: generator_input and domain only')
    parser.add_argument('--answer', action='append', choices=['true', 'false', 'neither'],
                        default=[], help='answer the next question; repeat in question order')
    parser.add_argument('--target', help='explicit reviewed module:function for the exported test')
    parser.add_argument('--export-test', type=Path, help='write a new file; never overwrite or run it')
    args = parser.parse_args()
    if bool(args.target) != bool(args.export_test):
        parser.error('--target and --export-test must be supplied together')
    if args.explain_conflict and not args.audit_policy:
        parser.error('--explain-conflict requires --audit-policy')
    if len(args.answer) > 64:
        parser.error('at most 64 answers are accepted')
    if args.export_policy and not args.suggest_cases:
        parser.error('--export-policy requires --suggest-cases')
    try:
        if args.policy or args.resume or args.examples:
            source = load_json(_read_input(args.policy or args.resume or args.examples, MAX_BYTES))
            if type(source) is not dict:
                raise ClarificationError('policy or session requires a JSON object')
            if args.examples or (args.resume and source.get('schema') == EXAMPLE_REVIEW_SCHEMA):
                result = example_result(args, source)
                print(json.dumps(result, indent=2, sort_keys=True))
                return
            session = (PolicySession.from_record(source) if args.resume and
                       source.get('schema') in (SESSION_SCHEMA, REVIEW_SCHEMA) else
                       Session.from_record(source) if args.resume else PolicySession(source))
        elif args.grid:
            content = _read_input(args.grid, 65536)
            if len(content) > 65536:
                raise ClarificationError('grid file exceeds 65536 bytes')
            source = json.loads(content, object_pairs_hook=unique_object)
        else:
            source = json.loads(files('executable_clarifications').joinpath(
                'resources/reviewed_candidates.json').read_text())['cases']['age_window']
            source = {key: source[key] for key in ('generator_input', 'domain')}
        if args.confirm_examples or args.audit_policy:
            raise ClarificationError('example confirmation/audit requires --examples or an example review --resume')
        if not (args.policy or args.resume) and (type(source) is not dict or set(source) != {'generator_input', 'domain'}):
            raise ClarificationError('grid requires only generator_input and domain')
        if not (args.policy or args.resume):
            session = Session(generate_candidates(source['generator_input']), source['domain'])
        if args.undo:
            if not isinstance(session, PolicySession):
                raise ClarificationError('--undo requires a custom policy session')
            session.undo()
        for answer in args.answer:
            question = session.question()
            if question is None:
                raise ClarificationError('no further question is available; remove excess answers')
            session.answer(question['id'], {'true': True, 'false': False, 'neither': None}[answer])
        if ((args.label_case or args.suggest_cases or args.compare_policy)
                and not isinstance(session, PolicySession)):
            raise ClarificationError('case labels/suggestions/comparison require a custom policy session')
        for label in args.label_case:
            case_id, separator, expected = label.partition('=')
            if not separator or expected not in ('true', 'false'):
                raise ClarificationError('case label must be ID=true or ID=false')
            session.label_case(case_id, expected == 'true')
        impact = None
        if args.compare_policy:
            impact = session.compare_policy(load_json(_read_input(args.compare_policy, MAX_BYTES)))
        outputs = []
        if args.save_session:
            outputs.append((args.save_session, canonical(session.export_record())))
        result = {'provenance': ('operator-reviewed declarative policy; operator answers'
                  if isinstance(session, PolicySession) else 'authored reviewed integer grid; operator answers'),
                  'status': session.status, 'question': session.question(),
                  'session': session.export_record(), 'observed_examples': session.examples(),
                  'scope': 'observed examples only; candidate agreement is not verified intent'}
        if impact is not None: result['policy_impact'] = impact
        if args.suggest_cases:
            result['suggestions'] = session.suggest_cases()
            if args.export_policy:
                outputs.append((args.export_policy, canonical(result['suggestions']['policy'])))
        if args.export_test:
            contract = render_contract(session, args.target)
            outputs.append((args.export_test, contract))
            result['test_written'] = str(args.export_test)
            result['execution'] = 'NOT RUN; review the target, then explicitly run the exported file'
        write_outputs(outputs)
    except (ClarificationError, OSError, ValueError, RecursionError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


def example_result(args, source):
    if args.answer or args.label_case or args.undo or args.suggest_cases or args.export_policy or args.compare_policy:
        raise ClarificationError('example sets do not accept policy questions, labels or suggestions')
    session = ExampleSet.from_record(source) if args.resume else ExampleSet(source)
    if args.confirm_examples: session.confirm()
    result = {'provenance': 'operator-supplied examples; explicit bulk review',
              'status': session.status, 'session': session.export_record(),
              'observed_examples': session.examples(), 'scope': 'supplied examples only; no completeness or authenticity proof'}
    if args.audit_policy:
        policy = load_json(_read_input(args.audit_policy, MAX_BYTES))
        result['audit'] = session.audit(policy)
        if args.explain_conflict:
            result['conflict_explanation'] = explain_conflict(session, policy)
    outputs = []
    if args.export_test:
        outputs.append((args.export_test, render_contract(session, args.target)))
        result['execution'] = 'NOT RUN; review the target, then explicitly run the exported file'
    if args.save_session: outputs.append((args.save_session, canonical(session.export_record())))
    write_outputs(outputs)
    return result



if __name__ == '__main__':
    main()
