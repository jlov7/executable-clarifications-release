"""Exclusive private export with best-effort rollback, not a crash transaction."""
import os

from .core import ClarificationError


def write_outputs(outputs):
    outputs = list(outputs)
    paths = [path.resolve() for path, _ in outputs]
    if len(set(paths)) != len(paths) or any(path.exists() for path in paths):
        raise ClarificationError('output paths must be distinct and new')
    if any(not path.parent.is_dir() for path in paths):
        raise ClarificationError('output parent directories must exist')
    # Encode the complete bundle before creating the first file.
    encoded = [(path, content.encode('utf-8')) for path, content in outputs]
    opened = []
    try:
        for path, _ in encoded:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_BINARY', 0), 0o600)
            try:
                stream = os.fdopen(fd, 'wb')
            except BaseException:
                # Stream construction may already have closed the descriptor.
                # Cleanup must neither replace the primary error nor skip unlink.
                try:
                    os.close(fd)
                except OSError:
                    pass
                try:
                    path.unlink()
                except OSError:
                    pass
                raise
            opened.append((path, stream))
        for (_, stream), (_, content) in zip(opened, encoded):
            if stream.write(content) != len(content):
                raise OSError('short output write')
            stream.close()
    except BaseException:
        for path, stream in opened:
            try:
                stream.close()
            except OSError:
                pass
            try:
                path.unlink()
            except OSError:
                pass
        raise
