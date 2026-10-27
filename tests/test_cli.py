import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CommandLine(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'executable_clarifications.cli', *args],
                              capture_output=True, text=True, timeout=10, check=False)

    def test_policy_output_preflight_preserves_files_on_invalid_export(self):
        policy = Path(__file__).parent / 'fixtures' / 'refund_policy.json'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for invalid, target in [('neither', 'implementation:decide'), ('true', 'bad-target')]:
                saved, contract = root / (invalid + '.json'), root / (invalid + '.py')
                result = self.run_cli('--policy', str(policy), '--answer', invalid,
                                      '--save-session', str(saved), '--target', target,
                                      '--export-test', str(contract))
                self.assertEqual(result.returncode, 2)
                self.assertFalse(saved.exists(), result.stderr)
                self.assertFalse(contract.exists(), result.stderr)
            shared = root / 'shared.json'
            result = self.run_cli('--policy', str(policy), '--answer', 'true',
                                  '--save-session', str(shared), '--target', 'implementation:decide',
                                  '--export-test', str(shared))
            self.assertEqual(result.returncode, 2)
            self.assertFalse(shared.exists(), result.stderr)

    def test_output_preflight_checks_every_parent_and_existing_file(self):
        policy = Path(__file__).parent / 'fixtures' / 'refund_policy.json'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saved = root / 'saved.json'
            existing = root / 'existing.py'
            existing.write_text('original')
            for contract in [existing, root / 'missing' / 'test.py']:
                result = self.run_cli('--policy', str(policy), '--answer', 'true',
                                      '--save-session', str(saved), '--target', 'implementation:decide',
                                      '--export-test', str(contract))
                self.assertEqual(result.returncode, 2)
                self.assertFalse(saved.exists())
                self.assertEqual(existing.read_text(), 'original')
            result = self.run_cli('--policy', str(policy), '--save-session', str(saved),
                                  '--suggest-cases', '--export-policy', str(saved))
            self.assertEqual(result.returncode, 2)
            self.assertFalse(saved.exists())

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO inputs require POSIX')
    def test_explicit_input_modes_refuse_fifo_without_waiting(self):
        known = Path(__file__).parent / 'fixtures' / 'known_examples.json'
        policy = Path(__file__).parent / 'fixtures' / 'refund_policy.json'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fifo = root / 'private-input'
            os.mkfifo(fifo)
            modes = [
                ['--examples', str(fifo)], ['--policy', str(fifo)],
                ['--grid', str(fifo)], ['--resume', str(fifo)],
                ['--examples', str(known), '--confirm-examples', '--audit-policy', str(fifo)],
                ['--policy', str(policy), '--compare-policy', str(fifo)]]
            for index, args in enumerate(modes):
                with self.subTest(mode=args[0], args=args[2:-1]):
                    output = root / f'output{index}.json'
                    try:
                        result = subprocess.run(
                            [sys.executable, '-m', 'executable_clarifications.cli',
                             *args, '--save-session', str(output)],
                            capture_output=True, text=True, timeout=1, check=False)
                    except subprocess.TimeoutExpired:
                        self.fail('FIFO input did not reject before timeout; child killed/reaped by subprocess.run')
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('regular file', result.stderr)
                    self.assertNotIn(str(fifo), result.stderr)
                    self.assertFalse(output.exists())

    def test_file_reader_preserves_regular_symlinks_and_refuses_directories(self):
        known = Path(__file__).parent / 'fixtures' / 'known_examples.json'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_cli('--examples', str(root))
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(str(root), result.stderr)
            if hasattr(os, 'symlink'):
                linked = root / 'linked.json'
                linked.symlink_to(known)
                result = self.run_cli('--examples', str(linked))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['status'], 'PENDING_REVIEW')

    def test_version_is_available_without_starting_a_review(self):
        from executable_clarifications import __version__
        result = self.run_cli('--version')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), __version__)

    def test_first_use_exposes_reviewed_session_and_question(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['provenance'], 'authored reviewed integer grid; operator answers')
        self.assertEqual(data['question']['input'], {'days': 21})
        self.assertEqual(data['session']['decisions'], [])

    def test_same_export_passes_correct_and_fails_wrong_separate_implementation(self):
        from importlib.resources import files
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / 'test_contract.py'
            result = self.run_cli('--answer', 'true', '--answer', 'true',
                                  '--target', 'implementation:decide',
                                  '--export-test', str(contract))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['status'], 'CANDIDATE_SET_NARROWED')
            self.assertEqual(len(data['session']['decisions']), 2)
            self.assertNotIn('from executable_clarifications', contract.read_text())
            for fixture, expected in [('correct', 0), ('wrong', 1)]:
                implementation = files('executable_clarifications').joinpath(
                    'resources', 'implementations', fixture, 'implementation.py').read_text()
                (root / 'implementation.py').write_text(implementation)
                run = subprocess.run([sys.executable, '-B', str(contract)], cwd=root,
                                     capture_output=True, text=True, timeout=10, check=False)
                self.assertEqual(run.returncode, expected, run.stderr)

    def test_export_requires_target_and_answers_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'contract.py'
            for args in [[], ['--target', 'implementation:decide'],
                         ['--answer', 'true'], ['--answer', 'neither',
                                                   '--target', 'implementation:decide']]:
                result = self.run_cli(*args, '--export-test', str(target))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(target.exists())
            target.write_text('keep me')
            result = self.run_cli('--answer', 'true', '--target', 'implementation:decide',
                                  '--export-test', str(target))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(target.read_text(), 'keep me')

    def test_grid_boundary_rejects_labels_malformed_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'grid.json'
            for content in ['{', '{}', ' ' * 65537,
                            '{"generator_input":{},"domain":[1],"labels":[]}']:
                path.write_text(content)
                result = self.run_cli('--grid', str(path))
                self.assertEqual(result.returncode, 2)
                self.assertNotIn('Traceback', result.stderr)

    def test_packaged_authored_resources_match_separate_regression_tables(self):
        from importlib.resources import files
        for name in ('reviewed_candidates.json', 'intended_behavior.json', 'refund_policy.json'):
            packaged = files('executable_clarifications').joinpath('resources', name).read_text()
            source = (Path(__file__).parent / 'fixtures' / name).read_text()
            self.assertEqual(json.loads(packaged), json.loads(source))

    def test_valid_operator_grid_and_ambiguous_json_boundary(self):
        source = {'generator_input': {'schema': 'executable-clarifications/integer-grid-v1',
                  'field': 'x', 'operators': ['<', '<='], 'thresholds': [10]}, 'domain': [10]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'grid.json'
            path.write_text(json.dumps(source))
            result = self.run_cli('--grid', str(path), '--answer', 'false')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'CANDIDATE_SET_NARROWED')
            # Duplicate keys have no unambiguous reviewed meaning, even when valid JSON parses.
            path.write_text(json.dumps(source).replace('"domain": [10]',
                                                       '"domain": [9], "domain": [10]'))
            result = self.run_cli('--grid', str(path))
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('Traceback', result.stderr)

    def test_cli_never_imports_target_and_bounds_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'contract.py'
            result = self.run_cli('--answer', 'true', '--target', 'nonexistent_module:decide',
                                  '--export-test', str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(target.exists())
        result = self.run_cli(*(['--answer', 'true'] * 65))
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('Traceback', result.stderr)
