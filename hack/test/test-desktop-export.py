#!/usr/bin/env python3
"""Check exported window classes without a running container or desktop."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "internal/inside-distrobox/assets/distrobox-export"


class WindowClassTests(unittest.TestCase):
    def test_exported_window_class(self):
        source = SCRIPT.read_text()
        block = source[source.index("\t\t# Preserve the application's window class:"):
                       source.index("\t\t# In case of an icon in a non canonical path")]
        block = block.replace("/run/host${host_home}", "${host_home}")
        for original, expected in (
            ("StartupWMClass=VSCodium\n", "VSCodium"),
            ("StartupWMClass=org.example.Editor\n", "org.example.Editor"),
            ("", "codium"),
            ("StartupWMClass=\n", "codium"),
        ):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp) / ".local/share/applications"
                directory.mkdir(parents=True)
                desktop = Path(tmp) / "codium.desktop"
                contents = "[Desktop Entry]\nName=Editor\n" + original + "Exec=codium %F\n"
                desktop.write_text(contents)
                exported = directory / "test-codium.desktop"
                exported.write_text(contents)
                env = dict(os.environ, host_home=tmp, desktop_file=str(desktop),
                           desktop_original_file=desktop.name,
                           desktop_home_file=exported.name)
                subprocess.run(["/bin/sh", "-ec", block], env=env, check=True)
                classes = [line for line in exported.read_text().splitlines()
                           if line.startswith("StartupWMClass=")]
                self.assertEqual(classes, ["StartupWMClass=" + expected])
                self.assertIn("Exec=codium %F", exported.read_text())


if __name__ == "__main__":
    unittest.main()
