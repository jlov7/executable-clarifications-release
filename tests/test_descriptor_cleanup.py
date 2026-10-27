"""Nested cleanup failures must not hide the triggering error or skip rollback."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from executable_clarifications import _output


class DescriptorCleanupTests(unittest.TestCase):
    def test_constructor_already_closed_descriptor_preserves_original(self):
        for error_type in (OSError, ValueError, KeyboardInterrupt):
            with self.subTest(error=error_type.__name__), tempfile.TemporaryDirectory() as name:
                path = Path(name) / 'output'
                primary = error_type('original constructor failure')

                def failing(fd, *args, primary=primary, **kwargs):
                    os.close(fd)
                    raise primary

                with patch.object(_output.os, 'fdopen', side_effect=failing), \
                        self.assertRaises(error_type) as caught:
                    _output.write_outputs([(path, 'private')])
                self.assertIs(caught.exception, primary)
                self.assertFalse(path.exists())

    def test_open_descriptor_is_closed_when_constructor_fails(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'output'
            descriptors = []
            primary = OSError('original constructor failure')

            def failing(fd, *args, **kwargs):
                descriptors.append(fd)
                raise primary

            with patch.object(_output.os, 'fdopen', side_effect=failing), \
                    self.assertRaises(OSError) as caught:
                _output.write_outputs([(path, 'private')])
            self.assertIs(caught.exception, primary)
            self.assertFalse(path.exists())
            with self.assertRaises(OSError):
                os.fstat(descriptors[0])

    def test_unlink_refusal_still_preserves_original_interruption(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'output'
            primary = KeyboardInterrupt('original interruption')

            def failing(fd, *args, **kwargs):
                os.close(fd)
                raise primary

            with patch.object(_output.os, 'fdopen', side_effect=failing), \
                    patch.object(Path, 'unlink', side_effect=PermissionError('refused')), \
                    self.assertRaises(KeyboardInterrupt) as caught:
                _output.write_outputs([(path, 'private')])
            self.assertIs(caught.exception, primary)
            self.assertTrue(path.exists())
            path.unlink()

    def test_later_constructor_failure_also_removes_earlier_output(self):
        with tempfile.TemporaryDirectory() as name:
            paths = [Path(name) / 'first', Path(name) / 'second']
            original = os.fdopen
            calls = 0
            primary = OSError('later constructor failure')

            def failing(fd, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    os.close(fd)
                    raise primary
                return original(fd, *args, **kwargs)

            with patch.object(_output.os, 'fdopen', side_effect=failing), \
                    self.assertRaises(OSError) as caught:
                _output.write_outputs([(path, 'private') for path in paths])
            self.assertIs(caught.exception, primary)
            self.assertFalse(any(path.exists() for path in paths))
