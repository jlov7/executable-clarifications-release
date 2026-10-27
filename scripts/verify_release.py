"""Local source gate. Optional HTTP browser check uses existing trusted Chromium."""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(browser=False):
    root = Path(__file__).resolve().parents[1]
    commands = [[sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                [sys.executable, 'scripts/build_session_demo.py', '--check'],
                ['node', '--check', 'web/app.js'], ['node', '--check', 'web/session-app.js'],
                ['node', '--check', 'web/policy-engine.js'], ['node', '--check', 'web/policy-editor.js'],
                ['node', '--check', 'web/review-state.js'], ['node', '--check', 'web/example-engine.js'], ['node', '--check', 'web/example-app.js'], ['node', 'tests/web-smoke.js']]
    if browser: commands.extend([[sys.executable, 'scripts/test_session_browser.py'],
                                 [sys.executable, 'scripts/test_add21_browser.py'],
                                 [sys.executable, 'scripts/test_suggestions_browser.py'],
                                 [sys.executable, 'scripts/test_examples_browser.py'],
                                 [sys.executable, 'scripts/test_recovery_browser.py'],
                                 [sys.executable, 'scripts/test_conflicts_browser.py'],
                                 [sys.executable, 'scripts/test_export_target_browser.py']])
    outcomes = []
    for command in commands:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=180, check=False)
        outcomes.append({'command': [Path(command[0]).name, *command[1:]],
                         'exit_code': result.returncode, 'output': result.stdout + result.stderr})
        if result.returncode:
            raise SystemExit(json.dumps({'status': 'FAIL', 'checks': outcomes}, indent=2))
    return {'status': 'PASS', 'checks': outcomes,
            'browser': 'HTTP Chromium' if browser else 'NOT RUN',
            'empirical_qualification': 'NOT RUN; authored mechanics only'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', action='store_true')
    print(json.dumps(run(parser.parse_args().browser), indent=2))
