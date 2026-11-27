#!/usr/bin/env bash
set -eu
exec python3 - "$@" <<'PY'
"""Scan the assembled app before signing. Inspect declarations, names and licence titles."""
import mmap
import os
from pathlib import Path
import re
import sys

if len(sys.argv) != 2 or not (Path(sys.argv[1]) / "Contents").is_dir():
    sys.exit("usage: scan-bundle-gpl.sh <app>")

root = Path(sys.argv[1])
retired = re.compile(r"espeak|pcaudio|kokoro[-_]onnx|phonemizer", re.I)
label = re.compile(rb"(?im)^(?:[^\w\r\n]*)(?:SPDX-License-Identifier|License(?:-Expression)?|Classifier):[^\r\n]*")
title = re.compile(rb"(?im)^[ \t]*(?:GNU (?:AFFERO |LESSER |LIBRARY )?GENERAL PUBLIC LICENSE|A?GPL(?:v?\d|-[123])?[.\w+-]*|LGPL[.\w+-]*)[ \t]*\r?$")
field = re.compile(rb"""(?i)(?:["']license(?:-expression)?["']\s*:\s*|\b__license__\s*=\s*)["']([^"'\r\n]+)["']""")
grant = re.compile(rb"(?im)^[ \t/*#-]*(?:this (?:file|project|program|software|library|package|module) is )?(?:licensed under|distributed under the terms of) [^\r\n]{0,160}")
license_name = re.compile(r"(?:^|[._-])(?:A?GPL)(?:$|[.v_-]|[123])", re.I)
family = re.compile(rb"\b(LGPL|GNU (?:Lesser|Library) General Public License|AGPL|GPL|GNU (?:Affero )?General Public License)(?=\b|v?\d)", re.I)
failed = False
# The GCC runtime library exception lets closed apps ship libgcc and libgfortran.
# NumPy's licence file declares it for those files, which some NumPy wheels
# carry. Allow that declaration only while none of those files are in the app
# (founder, 2026-11-26); if one appears, the declaration blocks again.
gcc_exception = re.compile(rb"\bWITH\s+GCC-exception-3\.1\b", re.I)
gcc_runtime = re.compile(r"^lib(?:gcc|gfortran|quadmath)", re.I)
gcc_present = any(gcc_runtime.match(name) for _, _, files in os.walk(root) for name in files)

def report(path, blocked):
    global failed
    failed |= blocked
    print(("BLOCKED" if blocked else "LGPL") + "  " + str(path.relative_to(root)))

def scan(path):
    with path.open("rb") as stream:
        head = stream.read(8192)
        if not head:
            return
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            if b"\0" in head:
                # Binary payloads may contain an explicit SPDX declaration.
                start = data.find(b"SPDX-License-Identifier:")
                while start >= 0:
                    line = re.split(rb"[\r\n\0]", data[start:start + 512], maxsplit=1)[0]
                    yield line
                    start = data.find(b"SPDX-License-Identifier:", start + 1)
            else:
                for pattern in (label, title, grant, field):
                    for match in pattern.finditer(data):
                        yield match.group()

def walk_error(error):
    raise error

for base, dirs, files in os.walk(root, onerror=walk_error):
    for name in dirs + files:
        path = Path(base) / name
        if retired.search(name) or license_name.search(name):
            report(path, True)
            continue
        if path.is_symlink() and not path.resolve().is_relative_to(root.resolve()):
            report(path, True)
            continue
        if name in dirs or path.is_symlink() or not path.is_file():
            continue
        lines = list(scan(path))
        excepted = [line for line in lines if gcc_exception.search(line)]
        if excepted and not gcc_present:
            # The file carries the full GPL-3 text that the exception amends; drop
            # its title too, but never an AGPL or other GPL declaration.
            gpl3_title = re.compile(rb"^\s*GNU GENERAL PUBLIC LICENSE\s*$", re.I)
            lines = [line for line in lines if not (gcc_exception.search(line) or gpl3_title.match(line))]
            print("EXCEPTION  " + str(path.relative_to(root)) + "  (GCC runtime exception; no GCC runtime file in the app)")
        kinds = {m[0].lower() for line in lines for m in family.finditer(line)}
        if kinds:
            report(path, bool(kinds - {b"lgpl", b"gnu lesser general public license", b"gnu library general public license"}))

sys.exit(int(failed))
PY
