import contextlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import review_post  # noqa: E402

MD = """---
repo: demo
pr: 7
verdict: %(verdict)s
last_head_sha: abc123
---

## Findings
| # | Sev | Conf | Status | Location | Issue |
|---|-----|------|--------|----------|-------|
| 1 | Med | high | 📋 drafted | pkg/a.go:2 | first issue |

## Inline comment drafts

### F1 — pkg/a.go:2
first draft body

### F2 — (whole PR)
whole-pr draft body
"""


def _fake_run(cmd, stdin=None, timeout=120):
    joined = " ".join(cmd)
    if "pulls/7/files" in joined:
        return 0, json.dumps({"filename": "pkg/a.go", "patch": "@@ -0,0 +1,3 @@\n+a\n+b\n+c"}) + "\n", ""
    if "headRefOid" in joined:
        return 0, "abc123\n", ""
    if "--approve" in joined:
        return 0, "", ""
    raise AssertionError("unexpected command: %r" % cmd)


@contextlib.contextmanager
def _fixture(verdict="approve-with-comments"):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "demo-7.md")
        with open(path, "w") as f:
            f.write(MD % {"verdict": verdict})
        orig_run = review_post.run
        review_post.run = _fake_run
        os.environ["MS_REVIEW_DRY_RUN"] = "1"
        try:
            yield path
        finally:
            review_post.run = orig_run
            os.environ.pop("MS_REVIEW_DRY_RUN", None)


def _rec(path, decision, drafts, subset_ok=False):
    extra = {"decision": decision, "drafts": drafts, "review_path": path}
    if subset_ok:
        extra["subset_ok"] = True
    return {"targets": ["https://github.com/o/demo/pull/7"], "extra": extra}


def test_subset_ok_drops_missing_drafts_and_says_so():
    with _fixture() as path:
        status, reply = review_post.execute(_rec(path, "post_findings", ["F1", "F9"], subset_ok=True))
        assert status == "done"
        assert "F1" in reply
        assert "dropped F9" in reply.replace("dropped", "dropped ").replace("  ", " ") or "F9" in reply


def test_subset_ok_awc_with_no_survivors_becomes_plain_approve():
    with _fixture() as path:
        status, reply = review_post.execute(_rec(path, "approve_with_comments", ["F9"], subset_ok=True))
        assert status == "done"
        assert "approve" in reply.lower()
        assert "F9" in reply  # the dropped draft is named


def test_subset_ok_refuses_a_contradicted_approve():
    with _fixture(verdict="request-changes") as path:
        try:
            review_post.execute(_rec(path, "approve_with_comments", ["F1"], subset_ok=True))
            raise AssertionError("expected Unpostable")
        except review_post.Unpostable as e:
            assert "request-changes" in str(e)


def test_subset_ok_refuses_contradicted_request_changes():
    with _fixture(verdict="approve-with-comments") as path:
        try:
            review_post.execute(_rec(path, "request_changes", ["F1"], subset_ok=True))
            raise AssertionError("expected Unpostable")
        except review_post.Unpostable as e:
            assert "approve" in str(e)


def test_without_subset_ok_missing_drafts_still_defer_to_master():
    with _fixture() as path:
        try:
            review_post.execute(_rec(path, "post_findings", ["F9"]))
            raise AssertionError("expected Unpostable")
        except review_post.Unpostable as e:
            assert "not found" in str(e)


def test_valid_line_posts_inline_in_dry_run():
    with _fixture() as path:
        status, reply = review_post.execute(_rec(path, "post_findings", ["F1"]))
        assert status == "done"
        assert "1 inline" in reply


def test_whole_pr_location_parses_and_lands_in_body():
    with _fixture() as path:
        status, reply = review_post.execute(_rec(path, "post_findings", ["F2"]))
        assert status == "done"
        assert "1 in body" in reply or "1 in the body" in reply


def test_partial_miss_without_subset_ok_defers_to_master():
    with _fixture() as path:
        try:
            review_post.execute(_rec(path, "post_findings", ["F1", "F9"]))
            raise AssertionError("expected Unpostable")
        except review_post.Unpostable as e:
            assert "F9" in str(e)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
