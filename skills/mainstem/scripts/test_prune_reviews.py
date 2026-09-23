import contextlib
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import prune_reviews  # noqa: E402


def test_classify_errors_splits_not_found_from_fatal():
    payload = {"errors": [
        {"type": "NOT_FOUND", "path": ["r1", "pullRequest"], "message": "Could not resolve to a PullRequest"},
        {"type": "RATE_LIMITED", "message": "API rate limit exceeded"},
    ]}
    not_found, fatal = prune_reviews.classify_errors(payload)
    assert not_found == {"r1"}
    assert fatal == ["API rate limit exceeded"]


def test_classify_errors_empty_payload():
    assert prune_reviews.classify_errors({}) == (set(), [])


@contextlib.contextmanager
def _scratch_board(reviews):
    """A throwaway dataDir/reviewsDir behind $MS_CONFIG, seeded with reviews.json + files."""
    with tempfile.TemporaryDirectory() as scratch:
        data_dir = os.path.join(scratch, "data")
        reviews_dir = os.path.join(scratch, "reviews")
        active = os.path.join(reviews_dir, "active")
        os.makedirs(data_dir)
        os.makedirs(active)
        with open(os.path.join(data_dir, "reviews.json"), "w") as f:
            json.dump(reviews, f)
        for e in reviews.values():
            with open(os.path.join(active, "%s-%s.md" % (e["repo"], e["pr"])), "w") as f:
                f.write("stub\n")
        cfg_path = os.path.join(scratch, "config.json")
        with open(cfg_path, "w") as f:
            json.dump({"dataDir": data_dir, "reviewsDir": reviews_dir}, f)
        old = os.environ.get("MS_CONFIG")
        os.environ["MS_CONFIG"] = cfg_path
        try:
            yield data_dir, active, os.path.join(reviews_dir, "archive")
        finally:
            if old is None:
                os.environ.pop("MS_CONFIG", None)
            else:
                os.environ["MS_CONFIG"] = old


def test_gone_pr_is_archived_despite_gh_nonzero_exit():
    # Regression: a re-created repo keeps its name but restarts PR numbering, so the old
    # number is NOT_FOUND, gh exits 1, and the run must still prune it — not die whole.
    reviews = {
        "https://github.com/o/alive/pull/7": {"repo": "alive", "pr": 7},
        "https://github.com/o/reborn/pull/40": {"repo": "reborn", "pr": 40},
    }
    urls = sorted(reviews)  # alive=r0, reborn=r1
    payload = {
        "data": {"r0": {"pullRequest": {"state": "OPEN", "headRefOid": "abc123"}}, "r1": None},
        "errors": [{"type": "NOT_FOUND", "path": ["r1", "pullRequest"],
                    "message": "Could not resolve to a PullRequest with the number of 40."}],
    }
    fake = types.SimpleNamespace(returncode=1, stdout=json.dumps(payload), stderr="gh: Could not resolve")
    with _scratch_board(reviews) as (data_dir, active, archive):
        orig = prune_reviews.subprocess.run
        prune_reviews.subprocess.run = lambda *a, **k: fake
        try:
            # keep the alias order the test's payload assumes
            assert urls == list(reviews)
            prune_reviews.main()
        finally:
            prune_reviews.subprocess.run = orig
        left = json.load(open(os.path.join(data_dir, "reviews.json")))
        assert list(left) == ["https://github.com/o/alive/pull/7"]
        assert left["https://github.com/o/alive/pull/7"]["live_head"] == "abc123"
        assert not os.path.exists(os.path.join(active, "reborn-40.md"))
        assert os.path.exists(os.path.join(archive, "reborn-40.md"))


def test_fatal_graphql_error_still_fails_the_run():
    reviews = {"https://github.com/o/alive/pull/7": {"repo": "alive", "pr": 7}}
    payload = {"data": {}, "errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]}
    fake = types.SimpleNamespace(returncode=1, stdout=json.dumps(payload), stderr="")
    with _scratch_board(reviews):
        orig = prune_reviews.subprocess.run
        prune_reviews.subprocess.run = lambda *a, **k: fake
        try:
            prune_reviews.main()
            raise AssertionError("expected SystemExit")
        except SystemExit as e:
            assert "rate limit" in str(e)
        finally:
            prune_reviews.subprocess.run = orig


def test_unparseable_gh_output_fails_the_run():
    reviews = {"https://github.com/o/alive/pull/7": {"repo": "alive", "pr": 7}}
    fake = types.SimpleNamespace(returncode=1, stdout="", stderr="gh: network unreachable")
    with _scratch_board(reviews):
        orig = prune_reviews.subprocess.run
        prune_reviews.subprocess.run = lambda *a, **k: fake
        try:
            prune_reviews.main()
            raise AssertionError("expected SystemExit")
        except SystemExit as e:
            assert "network unreachable" in str(e)
        finally:
            prune_reviews.subprocess.run = orig


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
