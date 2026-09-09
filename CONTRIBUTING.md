# Contributing

## Run demo mode

```bash
cd skills/mainstem/scripts
export MS_CONFIG=/tmp/ms-dev-config.json
echo '{"dataDir": "/tmp/ms-dev-data"}' > "$MS_CONFIG"
python3 ms_server.py --demo
```
Open http://127.0.0.1:7777.

## Run CI checks locally

```bash
find . -name '*.sh' -not -path './.git/*' -print0 | xargs -0 shellcheck
find . -name '*.py' -not -path './.git/*' -print0 | xargs -0 python3 -m py_compile
```
(See `.github/workflows/ci.yml` for the full check list, including the smoke test.)

## Pull requests

Keep them focused — one logical change per PR. Run the checks above before opening one.
