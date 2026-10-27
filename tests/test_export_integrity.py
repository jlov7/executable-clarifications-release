"""Exports are private at creation and ordinary partial failures are cleaned up."""
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from executable_clarifications import cli


class ExportIntegrityTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'POSIX permissions only')
    def test_private_from_creation_with_permissive_umask(self):
        with tempfile.TemporaryDirectory() as name:
            paths = [Path(name) / 'session.json', Path(name) / 'contract.py']
            previous = os.umask(0)
            try:
                cli.write_outputs([(path, 'private') for path in paths])
            finally:
                os.umask(previous)
            self.assertEqual([stat.S_IMODE(path.stat().st_mode) for path in paths], [0o600, 0o600])

    def test_later_open_failure_removes_only_this_invocations_files(self):
        with tempfile.TemporaryDirectory() as name:
            paths = [Path(name) / 'session.json', Path(name) / 'contract.py']
            original = os.open
            original_path_open = Path.open
            def failed(path, *args, **kwargs):
                if Path(path) == paths[1]:
                    raise OSError('synthetic late failure')
                return original(path, *args, **kwargs)
            def failed_path(path, *args, **kwargs):
                if path == paths[1]:
                    raise OSError('synthetic late failure')
                return original_path_open(path, *args, **kwargs)
            with patch('os.open', side_effect=failed), patch.object(Path, 'open', new=failed_path), \
                    self.assertRaises(OSError):
                cli.write_outputs([(path, 'private') for path in paths])
            self.assertFalse(any(path.exists() for path in paths))

    def test_encode_failure_creates_nothing(self):
        with tempfile.TemporaryDirectory() as name:
            paths = [Path(name) / 'session.json', Path(name) / 'contract.py']
            with self.assertRaises(UnicodeError):
                cli.write_outputs([(paths[0], 'safe'), (paths[1], '\ud800')])
            self.assertFalse(any(path.exists() for path in paths))

    def test_existing_files_and_duplicate_names_remain_protected(self):
        with tempfile.TemporaryDirectory() as name:
            paths = [Path(name) / 'session.json', Path(name) / 'contract.py']
            paths[1].write_text('keep')
            with self.assertRaises(ValueError):
                cli.write_outputs([(path, 'new') for path in paths])
            self.assertFalse(paths[0].exists())
            self.assertEqual(paths[1].read_text(), 'keep')
            with self.assertRaises(ValueError):
                cli.write_outputs([(paths[0], 'one'), (paths[0], 'two')])
            self.assertFalse(paths[0].exists())

    def test_close_failure_still_cleans_every_file_and_preserves_the_error(self):
        from executable_clarifications import _output
        with tempfile.TemporaryDirectory() as name:
            paths = [Path(name) / 'session.json', Path(name) / 'contract.py']
            original = os.fdopen
            failure = OSError('synthetic close failure')
            class BrokenClose:
                def __init__(self, stream): self.stream = stream
                def write(self, data): return self.stream.write(data)
                def close(self):
                    self.stream.close()
                    raise failure
            with patch.object(_output.os, 'fdopen', side_effect=lambda *a, **k: BrokenClose(original(*a, **k))), \
                    self.assertRaises(OSError) as caught:
                cli.write_outputs([(path, 'data') for path in paths])
            self.assertIs(caught.exception, failure)
            self.assertFalse(any(path.exists() for path in paths))
