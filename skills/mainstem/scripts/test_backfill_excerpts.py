import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import backfill_excerpts as m  # noqa: E402


def test_hunk_excerpt_finds_target_and_keeps_markers():
    patch = "@@ -10,3 +10,4 @@\n context\n-old line\n+new line\n+another new line\n more context"
    result = m.hunk_excerpt(patch, target=12)
    assert result is not None
    start, rows = result
    assert any(r.startswith("+new line") for r in rows)


def test_hunk_excerpt_returns_none_when_target_not_in_patch():
    patch = "@@ -1,2 +1,2 @@\n context\n-old\n+new"
    assert m.hunk_excerpt(patch, target=9999) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
