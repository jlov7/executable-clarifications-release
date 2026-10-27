"""Public documentation links and bundled illustration are part of the source artifact."""
import re
import struct
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DOCS = ["README.md", "CHANGELOG.md", "docs/VALIDATION.md", "CONTRIBUTING.md", "SECURITY.md", "docs/USAGE.md",
               "docs/DESIGN.md", "docs/EVALUATION.md", "docs/LIMITATIONS.md",
               "docs/REFERENCES.md", "docs/STABILITY.md"]


class PublicDocs(unittest.TestCase):
    def test_local_links_and_heading_anchors_exist(self):
        for name in PUBLIC_DOCS:
            source = ROOT / name
            for match in re.finditer(r"!?\[([^\]]*)\]\(([^)\s]+)\)", source.read_text()):
                target = urlsplit(match[2])
                if target.scheme or target.netloc:
                    continue
                with self.subTest(source=name, link=match[2]):
                    path = source.parent / unquote(target.path) if target.path else source
                    self.assertTrue(path.resolve().is_relative_to(ROOT))
                    self.assertTrue(path.is_file())
                    if target.fragment:
                        headings = re.findall(r"^#+\s+(.+)$", path.read_text(), re.MULTILINE)
                        anchors = {re.sub(r"[^\w -]", "", heading.lower()).replace(" ", "-") for heading in headings}
                        self.assertIn(unquote(target.fragment), anchors)

    def test_readme_illustration_has_alt_text_and_real_pixels(self):
        text = (ROOT / "README.md").read_text()
        match = re.search(r"!\[([^\]]+)\]\((docs/images/[^)]+\.png)\)", text)
        self.assertIsNotNone(match)
        data = (ROOT / match[2]).read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", data[16:24])
        self.assertGreaterEqual(width, 390)
        self.assertGreaterEqual(height, 300)
