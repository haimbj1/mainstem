import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import session_status_from_notes as m  # noqa: E402


def test_ticket_regex_empty_when_no_projects():
    pat = m.build_ticket_re([])
    assert pat.search("see PROJ-123 for context") is None


def test_ticket_regex_matches_configured_projects():
    pat = m.build_ticket_re(["PROJ", "WIDGET"])
    assert pat.search("see PROJ-123 for context").group(0) == "PROJ-123"
    assert pat.search("WIDGET-7 too") is not None
    assert pat.search("OTHER-1 not") is None


def test_repo_qualified_ref_precedes_bare_ref():
    note_head = ("---\nbranch: feat/x\n---\n"
                 "see https://github.com/acme/widgets/pull/6 and also #6")
    refs = m.extract_refs(note_head, branch="feat/x")
    assert refs[0] == "widgets#6"


def test_refs_capped_at_16():
    body = " ".join(f"#{i}" for i in range(1, 30))
    refs = m.extract_refs("---\nbranch: x\n---\n" + body, branch="x")
    assert len(refs) <= 16


def test_no_trunk_branch_match():
    # wt_by_path gives the session a real branch ("main") so the trunk-exclusion guard
    # (nb not in ("main", "master")) is the thing actually stopping the match, not branch
    # being falsy.
    hit = m.match_note(
        {"name": "s1", "cwd": "/work/repo"},
        [{"file": "other.md", "mtime": "z",
          "head": "---\nbranch: main\nworktree: /elsewhere\n---\nsomething"}],
        wt_by_path={"/work/repo": {"branch": "main"}}, cwd_shared=False, live_names={"s1"},
    )
    assert hit is None


def test_non_trunk_branch_does_match():
    hit = m.match_note(
        {"name": "s1", "cwd": "/work/repo"},
        [{"file": "other.md", "mtime": "z",
          "head": "---\nbranch: feat/x\nworktree: /elsewhere\n---\nsomething"}],
        wt_by_path={"/work/repo": {"branch": "feat/x"}}, cwd_shared=False, live_names={"s1"},
    )
    assert hit is not None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
