#!/usr/bin/env python3
"""Build the distributable zip for this skill.

    py scripts/package_skill.py                 # dist/markitdown-<version>.zip
    py scripts/package_skill.py --version 1.0.0 --out /tmp

The archive contains a single top-level directory named after the skill:

    markitdown/
    ├── SKILL.md
    ├── README.md
    ├── LICENSE
    ├── scripts/
    ├── references/
    └── evals/

That folder name has to match `name:` in SKILL.md, because the Agent Skills
specification requires the name to equal the parent directory name — so zipping
the repository root (markitdown-skill/) would produce a skill other
implementations reject.

Excluded: .git, __pycache__, *.pyc/.pyo, dist/. evals/fixtures/ is included when
present (it is gitignored and rebuilt by make_fixtures.py) so an unpacked copy can
run its own test suite offline; a missing fixtures/ directory only warns.

    py scripts/package_skill.py --flat --no-fixtures   # platform upload package

--flat puts SKILL.md at the archive root instead of under markitdown/, which is
what a skill marketplace (WorkBuddy / SkillPay) expects. --no-fixtures drops
evals/fixtures/: those are pdf/docx/xlsx/pptx/png/zip/wav files and the platform
rejects those types. --flat implies --no-fixtures.

Output is byte-reproducible: entries are sorted and carry a fixed timestamp, so
the same sources always hash the same.
"""

import argparse
import hashlib
import os
import re
import sys
import zipfile

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "dist", ".pytest_cache"}
# Build artifacts only. No content extension is filtered: evals/fixtures/sample.zip
# is a fixture, and excluding *.zip dropped exactly that one file — which showed
# up as a SKIP (not a failure) when the unpacked archive ran its own evals.
SKIP_EXTENSIONS = {".pyc", ".pyo"}
FIXED_TIME = (1980, 1, 1, 0, 0, 0)

# SKILL.md stays at the archive root; these are the only top-level entries that
# travel with it.
INCLUDE = ["SKILL.md", "README.md", "LICENSE", "scripts", "references", "evals"]


def read_frontmatter(path):
    """Return the frontmatter as a flat dict, with metadata values inlined.

    Only `key: value` lines and one level of nesting under `metadata:` are
    needed here, so no YAML parser (and no dependency) is required.
    """
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not match:
        return {}

    values = {}
    nested = None
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indented = line[:1] in (" ", "\t")
        key, _, value = line.strip().partition(":")
        if not value.strip() and not indented:
            nested = key.strip()
            continue
        if indented and nested:
            values[f"{nested}.{key.strip()}"] = value.strip().strip("\"'")
        else:
            nested = None
            values[key.strip()] = value.strip().strip("\"'")
    return values


def collect_files(root, include_fixtures=True):
    """Every file that belongs in the archive, as paths relative to root."""
    found = []
    for entry in INCLUDE:
        path = os.path.join(root, entry)
        if not os.path.exists(path):
            continue
        if os.path.isfile(path):
            found.append(entry)
            continue
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                if os.path.splitext(name)[1].lower() in SKIP_EXTENSIONS:
                    continue
                full = os.path.join(dirpath, name)
                relative = os.path.relpath(full, root).replace(os.sep, "/")
                if not include_fixtures and relative.startswith("evals/fixtures/"):
                    continue
                found.append(relative)
    return sorted(found)


def collect_vendor(vendor_dir):
    """(source_path, arcname) pairs for a tree that ships as vendor/python/.

    Used for the offline bundle: a standalone CPython plus markitdown that
    convert.py picks up before it ever looks for uv. Thousands of files, so the
    caller reports it as one summary line instead of listing every path.
    """
    entries = []
    for dirpath, dirnames, filenames in os.walk(vendor_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() in SKIP_EXTENSIONS:
                continue
            full = os.path.join(dirpath, name)
            relative = os.path.relpath(full, vendor_dir).replace(os.sep, "/")
            entries.append((full, f"vendor/python/{relative}"))
    return entries


def build(root, out_path, folder, entries):
    """Write the zip (entries are `(source_path, archive_relative)` pairs).

    An empty folder means the flat layout: entries land at the archive root.
    """
    prefix = f"{folder}/" if folder else ""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for source, relative in entries:
            info = zipfile.ZipInfo(f"{prefix}{relative}", date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            # 0644 for files, and 0755 for the scripts so an unpacked copy can
            # run them directly on Unix.
            executable = relative.endswith((".py", ".sh"))
            info.external_attr = (0o755 if executable else 0o644) << 16
            with open(source, "rb") as handle:
                archive.writestr(info, handle.read())

    digest = hashlib.sha256()
    with open(out_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def force_utf8_stdio():
    """Force UTF-8 on both streams.

    Windows capture pipes default to the ANSI code page, so the emoji in the
    summary line raise UnicodeEncodeError as soon as stdout is redirected — the
    same trap convert.py documents. The evals run this script with a captured
    stdout and no PYTHONUTF8, which is how that regression is caught.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass


def main():
    force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Zip this skill for distribution")
    parser.add_argument("--out", default=os.path.join(SKILL_ROOT, "dist"),
                        help="Directory for the .zip (default: <skill>/dist)")
    parser.add_argument("--version",
                        help="Version for the file name (default: metadata.version "
                             "from SKILL.md)")
    parser.add_argument("--vendor", metavar="DIR",
                        help="Ship DIR as vendor/python/ inside the archive "
                             "(offline bundle: a standalone interpreter that "
                             "already has markitdown installed)")
    parser.add_argument("--label", default="",
                        help="Extra suffix for the file name, e.g. offline-win64")
    parser.add_argument("--flat", action="store_true",
                        help="Put SKILL.md at the archive root (marketplace upload); "
                             "implies --no-fixtures")
    parser.add_argument("--no-fixtures", action="store_true",
                        help="Leave out evals/fixtures/ — the marketplace rejects "
                             "pdf/docx/xlsx/pptx/png/zip/wav")
    args = parser.parse_args()
    include_fixtures = not (args.flat or args.no_fixtures)

    frontmatter = read_frontmatter(os.path.join(SKILL_ROOT, "SKILL.md"))
    folder = frontmatter.get("name")
    if not folder:
        print("Error: SKILL.md has no `name:` in its frontmatter", file=sys.stderr)
        return 1

    if args.vendor and not os.path.isdir(args.vendor):
        print(f"Error: --vendor directory not found: {args.vendor}", file=sys.stderr)
        return 1

    version = args.version or frontmatter.get("metadata.version") or "0.0.0"
    if args.flat and args.vendor:
        print("Error: --flat is for marketplace upload; the offline bundle needs "
              "its markitdown/ folder", file=sys.stderr)
        return 1

    files = collect_files(SKILL_ROOT, include_fixtures=include_fixtures)
    entries = [(os.path.join(SKILL_ROOT, relative), relative) for relative in files]

    vendor_files = collect_vendor(args.vendor) if args.vendor else []
    entries += vendor_files

    stem = f"{folder}-{version}" + ("-skillpay" if args.flat else "")
    stem += f"-{args.label}" if args.label else ""
    # Flat means the archive is nothing but the skill: no outer folder at all.
    archive_folder = "" if args.flat else folder
    out_path = os.path.join(args.out, f"{stem}.zip")
    digest = build(SKILL_ROOT, out_path, archive_folder, entries)

    size = os.path.getsize(out_path)
    print(f"📦 {out_path}")
    if args.flat:
        print("   skill root: SKILL.md at the zip root (flat, for marketplace upload)")
    else:
        print(f"   skill folder: {folder}/  (matches name: in SKILL.md)")
    print(f"   version: {version}")
    print(f"   files: {len(files)}   size: {size / 1024:.1f} KiB")
    if not include_fixtures:
        print("   evals/fixtures/: left out (run evals/make_fixtures.py to rebuild "
              "them locally)")
    if vendor_files:
        vendor_bytes = sum(os.path.getsize(source) for source, _ in vendor_files)
        print(f"   vendor/python/: {len(vendor_files)} files, "
              f"{vendor_bytes / 1024 / 1024:.1f} MiB uncompressed")
        print("   → offline bundle: convert.py uses that interpreter and never "
              "calls uv")
    print(f"   sha256: {digest}")
    if include_fixtures and not any(f.startswith("evals/fixtures/") for f in files):
        print("⚠️  evals/fixtures/ is missing — run evals/make_fixtures.py before\n"
              "   packaging if the archive should run its evals without network.")
    print("\n   contents:")
    for relative in files:
        print(f"     {archive_folder + '/' if archive_folder else ''}{relative}")
    if vendor_files:
        print(f"     {folder}/vendor/python/  ({len(vendor_files)} files, "
              f"{vendor_bytes / 1024 / 1024:.1f} MiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
