import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# reviews_index.py runs its collection (glob + write reviews.json) at import time against
# whatever reviewsDir/dataDir the ambient config resolves to — point both at a throwaway
# scratch directory before importing it, so this test never touches a real machine's
# ~/.claude/reviews or ~/.local/share/mainstem.
_scratch = tempfile.mkdtemp(prefix="ms-test-reviews-index-")
os.makedirs(os.path.join(_scratch, "reviews", "active"), exist_ok=True)
os.makedirs(os.path.join(_scratch, "data"), exist_ok=True)
_cfg_path = os.path.join(_scratch, "config.json")
with open(_cfg_path, "w") as _f:
    json.dump({
        "dataDir": os.path.join(_scratch, "data"),
        "reviewsDir": os.path.join(_scratch, "reviews"),
    }, _f)
os.environ["MS_CONFIG"] = _cfg_path

import reviews_index as m  # noqa: E402


def test_parse_drafts_extracts_diff_marked_excerpt():
    body = (
        "### F1 — src/widgets.js:42\n"
        "```excerpt start=40 target=42 diff=1\n"
        " function clampWidth(w, max) {\n"
        "-  return w < max ? w : max - 1;\n"
        "+  return w <= max ? w : max;\n"
        " }\n"
        "```\n"
        "This clamps one pixel short of the container edge. Use <= here.\n"
    )
    drafts = m.parse_drafts(body, "https://github.com/example/demo/pull/12")
    assert len(drafts) == 1
    d = drafts[0]
    assert d["id"] == "F1"
    assert d["loc"] == "src/widgets.js:42"
    assert "clamps one pixel short" in d["text"]
    assert "```excerpt" not in d["text"]
    assert d["excerpt"] == {
        "start": 40, "target": 42, "diff": True,
        "code": " function clampWidth(w, max) {\n"
                "-  return w < max ? w : max - 1;\n"
                "+  return w <= max ? w : max;\n"
                " }",
    }
    assert d["file_url"].startswith("https://github.com/example/demo/pull/12/files#diff-")
    assert d["file_url"].endswith("R42")


def test_parse_drafts_without_excerpt_is_none():
    body = "### F2 — src/other.js:5\nNo excerpt here, just prose.\n"
    drafts = m.parse_drafts(body, "https://github.com/example/demo/pull/12")
    assert drafts[0]["excerpt"] is None
    assert drafts[0]["text"] == "No excerpt here, just prose."


def test_parse_drafts_without_url_has_no_file_url():
    body = "### F3 — src/other.js:5\nsome text\n"
    drafts = m.parse_drafts(body, "")
    assert drafts[0]["file_url"] is None


def test_parse_drafts_with_malformed_excerpt_degrades_to_none():
    body = (
        "### F4 — src/other.js:9\n"
        "```excerpt not-a-valid-header-format\n"
        "some code\n"
        "```\n"
        "Some prose about the defect.\n"
    )
    drafts = m.parse_drafts(body, "https://github.com/example/demo/pull/12")
    assert drafts[0]["excerpt"] is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
