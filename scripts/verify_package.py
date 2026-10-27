"""Install a supplied local wheel and exercise first use without source fallback.

Run with uv. Creates and removes its own environment under .release-scratch/.
The exported fixture contracts run explicitly here against reviewed owned code.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(wheel, browser=False):
    root = Path(__file__).resolve().parents[1]
    scratch = root / '.release-scratch'
    scratch.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    with tempfile.TemporaryDirectory(prefix='package-', dir=scratch) as directory:
        work = Path(directory)
        venv = work / 'venv'
        subprocess.run(['uv', 'venv', '--python', sys.executable, str(venv)],
                       check=True, env=env, timeout=30)
        python = venv / 'bin/python'
        subprocess.run(['uv', 'pip', 'install', '--python', str(python), '--no-deps', str(wheel)],
                       check=True, env=env, timeout=120)
        if browser:
            subprocess.run(['uv', 'pip', 'install', '--python', str(python), '-r',
                            str(root / 'requirements-release.txt')],
                           check=True, env=env, timeout=120)
        imported = subprocess.run([str(python), '-I', '-c',
            'import executable_clarifications; assert executable_clarifications.__version__ == \"1.2.0\"; print(executable_clarifications.__file__)'],
            cwd=work, env=env, check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        if not Path(imported).is_relative_to(venv):
            raise AssertionError('installed import escaped the isolated environment')
        suite = subprocess.run([str(python), '-I', '-m', 'unittest', 'discover', '-s',
                                str(root / 'tests'), '-v'], cwd=work, env=env,
                               capture_output=True, text=True, timeout=30, check=False)
        if suite.returncode:
            raise AssertionError(suite.stdout + suite.stderr)
        command = venv / 'bin/executable-clarifications'
        first = subprocess.run([str(command)], cwd=work, env=env, check=True,
                               capture_output=True, text=True, timeout=10)
        if json.loads(first.stdout)['question']['input'] != {'days': 21}:
            raise AssertionError('installed first question changed')
        export = work / 'contract.py'
        receipt = subprocess.run([str(command), '--answer', 'true', '--answer', 'true',
            '--target', 'implementation:decide', '--export-test', str(export)], cwd=work,
            env=env, check=True, capture_output=True, text=True, timeout=10)
        if json.loads(receipt.stdout)['status'] != 'CANDIDATE_SET_NARROWED':
            raise AssertionError('installed CLI did not record the authored answers')
        fixture_writer = '''from importlib.resources import files
from pathlib import Path
for name in ('correct', 'wrong'):
    directory = Path(name)
    directory.mkdir()
    directory.joinpath('implementation.py').write_text(files('executable_clarifications').joinpath(
        'resources', 'implementations', name, 'implementation.py').read_text())
'''
        subprocess.run([str(python), '-I', '-c', fixture_writer], cwd=work, env=env,
                       check=True, timeout=10)
        results = {}
        for name, expected in [('correct', 0), ('wrong', 1)]:
            target = work / name / 'test_contract.py'
            target.write_bytes(export.read_bytes())
            result = subprocess.run([str(python), '-B', str(target)], cwd=target.parent,
                                    env=env, capture_output=True, text=True, timeout=10, check=False)
            if result.returncode != expected:
                raise AssertionError(name + ': ' + result.stderr)
            results[name] = {'exit_code': result.returncode, 'expected': expected,
                             'test_output': result.stderr.strip()}
        neither = subprocess.run([str(command), '--answer', 'neither', '--target',
            'implementation:decide', '--export-test', str(work / 'blocked.py')],
            cwd=work, env=env, capture_output=True, text=True, timeout=10, check=False)
        if neither.returncode != 2 or (work / 'blocked.py').exists():
            raise AssertionError('neither must block assertion export')
        browser_checks = []
        if browser:
            for script in ('test_session_browser.py', 'test_add21_browser.py',
                           'test_suggestions_browser.py', 'test_examples_browser.py',
                           'test_recovery_browser.py', 'test_conflicts_browser.py',
                           'test_export_target_browser.py'):
                result = subprocess.run([str(python), 'scripts/' + script], cwd=root, env=env,
                                        capture_output=True, text=True, timeout=180, check=False)
                if result.returncode:
                    raise AssertionError(script + '\n' + result.stdout + result.stderr)
                browser_checks.append({'command': ['python', 'scripts/' + script],
                                       'exit_code': result.returncode,
                                       'output': (result.stdout + result.stderr).strip()})
        return {'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
                'verification_scratch': str(work),
                'import': 'isolated site-packages verified', 'first_question': {'days': 21},
                'installed_suite': {'exit_code': 0, 'output': suite.stderr.strip()},
                'contract_sha256': hashlib.sha256(export.read_bytes()).hexdigest(),
                'same_contract_results': results, 'neither_export': 'blocked',
                'browser_checks': browser_checks,
                'browser': 'HTTP Chromium with installed wheel and source UI' if browser else 'NOT RUN',
                'provenance': 'authored fixtures; no model or human study'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', type=Path)
    parser.add_argument('--browser', action='store_true', help='use existing trusted Chromium')
    args = parser.parse_args()
    print(json.dumps(run(args.wheel.resolve(), args.browser), indent=2))
