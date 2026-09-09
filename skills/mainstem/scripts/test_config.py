import contextlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config  # noqa: E402


@contextlib.contextmanager
def _isolated_home():
    """Point ~ at an empty scratch dir so a real ~/.config/mainstem/config.json on the
    machine running these tests can never leak into an assertion about defaults/injected
    values."""
    with tempfile.TemporaryDirectory() as scratch_home:
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = scratch_home
        try:
            yield scratch_home
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


@contextlib.contextmanager
def _no_repo_local_config():
    """Guarantee <repo>/config.local.json doesn't leak into a test, without ever deleting
    a real one a developer might have — moves it aside for the duration, then restores it."""
    path = os.path.join(config.REPO_ROOT, "config.local.json")
    moved = path + ".test-backup"
    existed = os.path.isfile(path)
    if existed:
        os.rename(path, moved)
    try:
        yield
    finally:
        if existed:
            os.rename(moved, path)


def test_defaults_when_no_files():
    with _isolated_home(), _no_repo_local_config():
        os.environ.pop("MS_CONFIG", None)
        cfg = config.load_config()
        assert cfg["brand"] == "MainStem"
        assert cfg["modules"]["reviews"] is True
        assert cfg["modules"]["jira"] is False


def test_env_override_layers_over_defaults():
    with _isolated_home(), _no_repo_local_config():
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"brand": "Test Board", "modules": {"jira": True}}, f)
            path = f.name
        try:
            os.environ["MS_CONFIG"] = path
            cfg = config.load_config()
            assert cfg["brand"] == "Test Board"
            assert cfg["modules"]["jira"] is True
            assert cfg["modules"]["reviews"] is True  # untouched sibling survives deep merge
        finally:
            os.environ.pop("MS_CONFIG", None)
            os.unlink(path)


def test_path_keys_are_expanded_absolute():
    with _isolated_home(), _no_repo_local_config():
        os.environ.pop("MS_CONFIG", None)
        cfg = config.load_config()
        assert os.path.isabs(cfg["dataDir"])
        assert not cfg["dataDir"].startswith("~")


def test_cli_get():
    env = dict(os.environ)
    env.pop("MS_CONFIG", None)
    with tempfile.TemporaryDirectory() as scratch_home:
        env["HOME"] = scratch_home
        out = subprocess.run(
            [sys.executable, os.path.join(HERE, "config.py"), "get", "port"],
            capture_output=True, text=True, check=True, env=env,
        )
    assert out.stdout.strip() == "7777"


def test_cli_get_missing_key_exits_nonzero():
    env = dict(os.environ)
    env.pop("MS_CONFIG", None)
    with tempfile.TemporaryDirectory() as scratch_home:
        env["HOME"] = scratch_home
        out = subprocess.run(
            [sys.executable, os.path.join(HERE, "config.py"), "get", "nope.nope"],
            capture_output=True, text=True, env=env,
        )
    assert out.returncode == 1


def test_env_var_outranks_user_config():
    # $MS_CONFIG is the most specific override (a one-off file for a single run) and must
    # win over the user's standing ~/.config/mainstem/config.json — regression test for the
    # precedence bug where the merge order had this backwards.
    with _isolated_home() as scratch_home, _no_repo_local_config():
        user_config_dir = os.path.join(scratch_home, ".config", "mainstem")
        os.makedirs(user_config_dir)
        with open(os.path.join(user_config_dir, "config.json"), "w") as f:
            json.dump({"brand": "User Config Board", "port": 1111}, f)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"brand": "Env Var Board"}, f)
            env_path = f.name
        try:
            os.environ["MS_CONFIG"] = env_path
            cfg = config.load_config()
            assert cfg["brand"] == "Env Var Board"  # env var wins over user config
            assert cfg["port"] == 1111  # user config still beats bare defaults
        finally:
            os.environ.pop("MS_CONFIG", None)
            os.unlink(env_path)


def test_repo_root_points_at_actual_repo_root():
    # REPO_ROOT must be the repo root itself (the parent of skills/), not skills/ or any
    # other ancestor — regression test for the off-by-one that made config.local.json
    # never load from where the docs say it does.
    assert os.path.basename(config.REPO_ROOT) != "skills"
    assert os.path.isdir(os.path.join(config.REPO_ROOT, "skills"))
    assert os.path.isfile(os.path.join(config.REPO_ROOT, "README.md"))


def test_repo_local_config_json_actually_loads():
    # Each documented layer must load from its documented location. This writes a real
    # config.local.json at the real REPO_ROOT (backing up/restoring any that already exists)
    # and confirms load_config() actually picks it up.
    with _isolated_home():
        os.environ.pop("MS_CONFIG", None)
        path = os.path.join(config.REPO_ROOT, "config.local.json")
        existed = os.path.isfile(path)
        backup = path + ".test-backup"
        if existed:
            os.rename(path, backup)
        try:
            with open(path, "w") as f:
                json.dump({"brand": "Repo Local Board"}, f)
            cfg = config.load_config()
            assert cfg["brand"] == "Repo Local Board"
        finally:
            os.unlink(path)
            if existed:
                os.rename(backup, path)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
