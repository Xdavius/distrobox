#!/usr/bin/env python3
"""Check exported window classes without a running container or desktop."""

import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "internal/inside-distrobox/assets/distrobox-export"


class WindowClassTests(unittest.TestCase):
    def test_exported_window_class(self):
        source = SCRIPT.read_text()
        block = source[source.index("\t\t# Prefer the native Wayland identity"):
                       source.index("\t\t# In case of an icon in a non canonical path")]
        block = block.replace("/run/host${host_home}", "${host_home}")
        for original, detected, expected in (
            ("StartupWMClass=VSCodium\n", "", "VSCodium"),
            ("StartupWMClass=VSCodium\n", "codium", "codium"),
            ("StartupWMClass=org.example.Editor\n", "", "org.example.Editor"),
            ("", "", "codium"),
            ("StartupWMClass=\n", "", "codium"),
        ):
            with self.subTest(original=original, detected=detected), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp) / ".local/share/applications"
                directory.mkdir(parents=True)
                desktop = Path(tmp) / "codium.desktop"
                contents = "[Desktop Entry]\nName=Editor\n" + original + "Exec=codium %F\n"
                desktop.write_text(contents)
                exported = directory / "test-codium.desktop"
                exported.write_text(contents)
                env = dict(os.environ, DETECTED_CLASS=detected, host_home=tmp, desktop_file=str(desktop),
                           desktop_original_file=desktop.name,
                           desktop_home_file=exported.name)
                subprocess.run(["/bin/sh", "-ec",
                                'electron_wayland_window_class() { printf "%s" "$DETECTED_CLASS"; }\n' + block],
                               env=env, check=True)
                classes = [line for line in exported.read_text().splitlines()
                           if line.startswith("StartupWMClass=")]
                self.assertEqual(classes, ["StartupWMClass=" + expected])
                self.assertIn("Exec=codium %F", exported.read_text())


class ElectronMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "python3").symlink_to(shutil.which("python3"))
        self.package = self.root / "resources/app/package.json"
        self.package.parent.mkdir(parents=True)
        self.package.write_text(json.dumps({"desktopName": "codium.desktop"}))
        self.env = dict(os.environ, PATH=str(self.bin), WAYLAND_DISPLAY="wayland-test",
                        PACKAGE_FILE=str(self.package))
        source = SCRIPT.read_text()
        self.function = source[source.index("electron_wayland_window_class()"):
                               source.index("# export_application will export")]

    def stub(self, name, script):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + script)
        path.chmod(0o755)

    def run_detection(self):
        result = subprocess.run(["/bin/sh", "-ec", self.function +
                                 "\nelectron_wayland_window_class /test/app.desktop"],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def pacman(self):
        self.stub("pacman", 'if [ "$1" = -Qoq ]; then echo app; else printf "%s\\n" "$PACKAGE_FILE"; fi\n')

    def test_package_managers(self):
        for name, script in (
            ("pacman", 'if [ "$1" = -Qoq ]; then echo app; else printf "%s\\n" "$PACKAGE_FILE"; fi'),
            ("dpkg-query", 'if [ "$1" = -S ]; then echo "app: /test/app.desktop"; else printf "%s\\n" "$PACKAGE_FILE"; fi'),
            ("rpm", 'if [ "$1" = -qf ]; then echo app; else printf "%s\\n" "$PACKAGE_FILE"; fi'),
        ):
            with self.subTest(manager=name):
                self.stub(name, script)
                self.assertEqual(self.run_detection(), "codium")
                (self.bin / name).unlink()

    def test_preserve_source_on_missing_or_invalid_metadata(self):
        self.pacman()
        for contents in ("{}", "invalid JSON", '{"desktopName": "../bad.desktop"}',
                         '{"desktopName": "bad\\nName=injected.desktop"}',
                         '{"desktopName": null}'):
            with self.subTest(contents=contents):
                self.package.write_text(contents)
                self.assertEqual(self.run_detection(), "")

    def test_ambiguous_package(self):
        self.stub("pacman", 'if [ "$1" = -Qoq ]; then echo app; else printf "%s\\n%s\\n" "$PACKAGE_FILE" /other/resources/app/package.json; fi')
        self.assertEqual(self.run_detection(), "")

    def test_unavailable_tools_or_x11(self):
        self.assertEqual(self.run_detection(), "")
        self.pacman()
        self.env["WAYLAND_DISPLAY"] = ""
        self.assertEqual(self.run_detection(), "")
        self.env["WAYLAND_DISPLAY"] = "wayland-test"
        (self.bin / "python3").unlink()
        self.assertEqual(self.run_detection(), "")

    def test_package_query_failure(self):
        self.stub("pacman", "exit 1")
        self.assertEqual(self.run_detection(), "")

    def test_package_query_timeout(self):
        self.stub("pacman", "while :; do :; done")
        self.assertEqual(self.run_detection(), "")


if __name__ == "__main__":
    unittest.main()
