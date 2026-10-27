"""Extract a local sdist and repeat installed source first use and checks."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def run(archive, browser=False):
    scratch = Path(__file__).resolve().parents[1] / '.release-scratch'
    scratch.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    with tempfile.TemporaryDirectory(prefix='sdist-', dir=scratch) as directory:
        work = Path(directory)
        with tarfile.open(archive, 'r:gz') as stream:
            members = stream.getmembers()
            if len(members) > 500 or sum(member.size for member in members) > 10_000_000:
                raise ValueError('source archive exceeds verification limits')
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                    raise ValueError('unsafe source archive member')
            stream.extractall(work, filter='data')
        roots = list(work.iterdir())
        if len(roots) != 1 or not roots[0].is_dir():
            raise ValueError('source archive requires exactly one root directory')
        source = roots[0]
        required = ['LICENSE', 'README.md', 'pyproject.toml', 'requirements-release.txt',
                    'requirements-lint.txt', 'docs/STABILITY.md', 'docs/images/known-examples.png',
                    'tests/fixtures/reviewed_candidates.json', 'tests/fixtures/intended_behavior.json',
                    'scripts/run_authored_example.py', 'scripts/serve_session_demo.py',
                    'web/session-data.js', 'web/session-data.sha256', 'web/session.html',
                    'web/policy-engine.js', 'web/policy-editor.js', 'scripts/test_add21_browser.py', 'tests/review-parity.js', 'web/refund-policy.json',
                    'src/executable_clarifications/resources/refund_policy.json',
                    'tests/fixtures/refund_policy.json', 'tests/policy-parity.js',
                    'tests/test_suggestions.py', 'tests/suggestion-parity.js',
                    'scripts/test_suggestions_browser.py', 'scripts/test_examples_browser.py',
                    'web/example-engine.js', 'web/example-app.js', 'web/review-state.js',
                    'scripts/test_recovery_browser.py', 'scripts/test_conflicts_browser.py',
                    'scripts/test_export_target_browser.py', 'tests/test_export_target_parity.py',
                    'tests/conflict-parity.js', 'tests/test_examples.py',
                    'tests/examples-parity.js', 'tests/fixtures/known_examples.json',
                    'tests/fixtures/known_examples_candidates.json']
        for name in required:
            if not (source / name).is_file():
                raise AssertionError('missing source resource: ' + name)
        private = ['AGENTS.md', 'STATUS.md', 'LICENSE-STATUS.md', 'docs/CODEX-HANDOFF.md',
                   'docs/PRD.md', 'docs/CONTINUATION-2026-10-19.md']
        if any((source / name).exists() for name in private):
            raise AssertionError('private planning included in source distribution')
        venv = work / 'venv'
        subprocess.run(['uv', 'venv', '--python', sys.executable, str(venv)],
                       check=True, env=env, timeout=30)
        python = venv / 'bin/python'
        subprocess.run(['uv', 'pip', 'install', '--python', str(python), '-r',
                        str(source / 'requirements-release.txt'), str(source)],
                       check=True, env=env, timeout=120)
        commands = [[str(python), '-I', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                    [str(python), 'scripts/build_session_demo.py', '--check'],
                    [str(python), 'scripts/run_authored_example.py'],
                    ['node', '--check', 'web/app.js'], ['node', '--check', 'web/session-app.js'],
                    ['node', '--check', 'web/policy-engine.js'], ['node', '--check', 'web/policy-editor.js'],
                    ['node', '--check', 'web/review-state.js'], ['node', '--check', 'web/example-engine.js'], ['node', '--check', 'web/example-app.js'],
                    ['node', 'tests/web-smoke.js']]
        if browser:
            commands.extend([[str(python), 'scripts/test_session_browser.py'],
                             [str(python), 'scripts/test_add21_browser.py'],
                             [str(python), 'scripts/test_suggestions_browser.py'],
                             [str(python), 'scripts/test_examples_browser.py'],
                             [str(python), 'scripts/test_recovery_browser.py'],
                             [str(python), 'scripts/test_conflicts_browser.py'],
                             [str(python), 'scripts/test_export_target_browser.py']])
        outcomes = []
        for command in commands:
            result = subprocess.run(command, cwd=source, env=env, capture_output=True,
                                    text=True, timeout=120, check=False)
            if result.returncode:
                raise AssertionError(' '.join(command[1:]) + '\n' + result.stdout + result.stderr)
            outcomes.append({'command': [Path(command[0]).name, *command[1:]], 'exit_code': 0,
                             'output': (result.stdout + result.stderr).strip()})
        return {'sdist_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'verification_scratch': str(work),
                'required_resources': 'present', 'private_planning': 'excluded',
                'checks': outcomes, 'browser': 'HTTP Chromium' if browser else 'NOT RUN'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--browser', action='store_true', help='use existing trusted Chromium')
    args = parser.parse_args()
    print(json.dumps(run(args.archive.resolve(), args.browser), indent=2))
