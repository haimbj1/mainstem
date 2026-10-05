import json
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import review_progress as rp  # noqa: E402

URL = "https://github.com/demo-org/demo-app/pull/12"


def _raises(exc, fn, *args, **kw):
    try:
        fn(*args, **kw)
    except exc:
        return
    raise AssertionError("expected %s" % exc.__name__)


def test_url_maps_to_one_file_per_pr():
    assert os.path.basename(rp.entry_path("/p", URL)) == "demo-org__demo-app__12.json"


def test_url_mapping_keeps_hyphenated_owner_and_repo_apart():
    a = rp.entry_path("/p", "https://github.com/a-b/c/pull/1")
    b = rp.entry_path("/p", "https://github.com/a/b-c/pull/1")
    assert a != b


def test_non_pr_url_is_rejected():
    _raises(ValueError, rp.entry_path, "/p", "https://github.com/o/r/issues/3")


def test_start_writes_first_step():
    with tempfile.TemporaryDirectory() as d:
        rp.start(d, URL)
        e = rp.load_all(d)[0]
        assert (e["url"], e["step"], e["error"]) == (URL, "context", None)


def test_step_records_file_counts():
    with tempfile.TemporaryDirectory() as d:
        rp.start(d, URL)
        rp.step(d, URL, "files", done=6, total=14)
        e = rp.load_all(d)[0]
        assert (e["step"], e["done"], e["total"]) == ("files", 6, 14)


def test_step_keeps_start_time():
    with tempfile.TemporaryDirectory() as d:
        rp.start(d, URL)
        started = rp.load_all(d)[0]["started_at"]
        rp.step(d, URL, "diff")
        assert rp.load_all(d)[0]["started_at"] == started


def test_bad_step_name_is_rejected():
    with tempfile.TemporaryDirectory() as d:
        rp.start(d, URL)
        _raises(ValueError, rp.step, d, URL, "lint")


def test_counts_outside_files_step_are_rejected():
    with tempfile.TemporaryDirectory() as d:
        rp.start(d, URL)
        _raises(ValueError, rp.step, d, URL, "diff", 1, 2)


def test_step_without_start_fails():
    with tempfile.TemporaryDirectory() as d:
        _raises(FileNotFoundError, rp.step, d, URL, "diff")


def test_finish_removes_entry():
    with tempfile.TemporaryDirectory() as d:
        rp.start(d, URL)
        rp.finish(d, URL)
        assert rp.load_all(d) == []


def test_fail_records_reason():
    with tempfile.TemporaryDirectory() as d:
        rp.start(d, URL)
        rp.fail(d, URL, "gh pr diff timed out")
        assert rp.load_all(d)[0]["error"] == "gh pr diff timed out"


def test_restart_clears_previous_error():
    with tempfile.TemporaryDirectory() as d:
        rp.fail(d, URL, "boom")
        rp.start(d, URL)
        assert rp.load_all(d)[0]["error"] is None


def test_concurrent_prs_keep_separate_entries():
    other = "https://github.com/demo-org/demo-app/pull/13"
    with tempfile.TemporaryDirectory() as d:
        rp.start(d, URL)
        rp.start(d, other)
        rp.step(d, other, "verdict")
        assert {e["url"]: e["step"] for e in rp.load_all(d)} == {URL: "context", other: "verdict"}


def test_reader_never_sees_a_partial_file():
    # The page polls while the agent writes: every read must parse, mid-write or not.
    with tempfile.TemporaryDirectory() as d:
        rp.start(d, URL)
        path = rp.entry_path(d, URL)
        stop, bad = threading.Event(), []

        def poll():
            while not stop.is_set():
                with open(path) as f:
                    raw = f.read()
                try:
                    json.loads(raw)
                except ValueError:
                    bad.append(raw)

        t = threading.Thread(target=poll)
        t.start()
        for i in range(400):
            rp.step(d, URL, "files", done=i % 15, total=14 + i)
        stop.set()
        t.join()
        assert bad == []


def test_load_all_skips_unreadable_files():
    with tempfile.TemporaryDirectory() as d:
        rp.start(d, URL)
        with open(os.path.join(d, "broken.json"), "w") as f:
            f.write('{"url": "half')
        assert [e["url"] for e in rp.load_all(d)] == [URL]


def test_load_all_of_missing_dir_is_empty():
    assert rp.load_all("/nonexistent/review_progress") == []


def test_prune_drops_only_stale_entries():
    other = "https://github.com/demo-org/demo-app/pull/13"
    with tempfile.TemporaryDirectory() as d:
        rp.start(d, URL)
        rp.start(d, other)
        old = time.time() - rp.STALE_FILE_SECONDS - 60
        os.utime(rp.entry_path(d, URL), (old, old))
        rp.prune_stale(d)
        assert [e["url"] for e in rp.load_all(d)] == [other]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
