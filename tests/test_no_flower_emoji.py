"""
Regression test: Verify that the flower emoji (\\U0001F338)
is completely eliminated from all source files and never reintroduced.
"""
import os
import pytest

IGNORED_DIRS = {
    'node_modules', 'venv', '.git', '__pycache__', 'build', '.gradle', 'dist', '.pytest_cache'
}
SOURCE_EXTENSIONS = (
    '.py', '.js', '.html', '.css', '.kt', '.xml', '.md', '.bat', '.yml'
)
FLOWER_EMOJI = chr(0x1F338)

def test_zero_flower_emoji_in_source():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    violations = []

    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for f in files:
            if f.endswith(SOURCE_EXTENSIONS):
                if f == "test_no_flower_emoji.py":
                    continue
                path = os.path.join(root, f)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        for line_no, line in enumerate(fh, start=1):
                            if FLOWER_EMOJI in line:
                                rel_path = os.path.relpath(path, root_dir)
                                violations.append(f"{rel_path}:{line_no} -> {line.strip()[:60]}")
                except Exception:
                    pass

    assert not violations, f"Flower emoji found in {len(violations)} locations:\n" + "\n".join(violations[:20])
