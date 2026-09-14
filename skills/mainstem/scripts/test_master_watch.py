import contextlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import master_watch  # noqa: E402

SCRIPT = os.path.join(HERE, "master_watch.py")


@contextlib.contextmanager
def _scratch_config():
    """A throwaway dataDir behind $MS_CONFIG so tests never touch the real lock."""
    with tempfile.TemporaryDirectory() as scratch:
        data_dir = os.path.join(scratch, "data")
        cfg_path = os.path.join(scratch, "config.json")
        with open(cfg_path, "w") as f:
            json.dump({"dataDir": data_dir}, f)
        env = dict(os.environ)
        env["MS_CONFIG"] = cfg_path
        yield os.path.join(data_dir, "master.lock"), env


def _probe(env):
    return subprocess.run(
        [sys.executable, SCRIPT, "--probe"],
        capture_output=True, text=True, env=env,
    )


def test_acquire_on_fresh_datadir_writes_pid():
    with _scratch_config() as (lock_path, _env):
        lock = master_watch.acquire(lock_path)
        try:
            assert lock is not None
            with open(lock_path) as f:
                assert int(f.read().strip()) == os.getpid()
        finally:
            lock.close()


def test_second_master_is_refused_while_lock_held():
    with _scratch_config() as (lock_path, env):
        lock = master_watch.acquire(lock_path)
        try:
            out = _probe(env)
            assert out.returncode == 1
            assert "REFUSED" in out.stdout
            assert str(os.getpid()) in out.stdout  # names the live holder
            assert "alive" in out.stdout
        finally:
            lock.close()


def test_stale_lock_file_never_blocks():
    # A leftover file with a dead pid and no flock (kill -9, reboot) must not block:
    # the lock is the flock, which the kernel released with the holder — the file is
    # only diagnostics.
    with _scratch_config() as (lock_path, env):
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        with open(lock_path, "w") as f:
            f.write("99999999\n")
        out = _probe(env)
        assert out.returncode == 0
        assert "acquired" in out.stdout


def test_lock_is_released_when_holder_exits():
    with _scratch_config() as (_lock_path, env):
        first = _probe(env)
        second = _probe(env)
        assert first.returncode == 0
        assert second.returncode == 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
