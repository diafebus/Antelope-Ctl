# Contributing

Current hardware development targets **Orion Studio Synergy Core only**. Other
profiles remain useful reference data; new device work needs its own evidence
and an explicit scope change. Read [AGENTS.md](AGENTS.md) and [SCOPE.md](SCOPE.md)
before changing device contracts.

## Start without hardware

Use Linux, Git, Python **3.11 or newer**, and Node.js **24** for the contributor
workflow. CI exercises Python 3.11 and 3.14 with Node 24. The CLI/protocol core
is standard-library-only. The offline suite also needs no pip or npm packages,
browser, USB permissions, vendor software, or packet-capture tools.

From a fresh clone:

```sh
git clone https://github.com/diafebus/Antelope-Ctl.git
cd Antelope-Ctl
python3 --version
node --version
python3 -m venv .venv
. .venv/bin/activate
python3 -m antelope.cli --help
python3 tools/offline_checks.py
```

Some Linux distributions package Python's `venv` support separately. Install
that support if environment creation fails. Run commands from the repository
root; there is no package-install or frontend-build step. The suite runs Python
unittests and six Node checks using built-in modules and simulated boundaries.
It never opens HID nodes or reads the private capture archive. `--python-only`
is useful for a focused check but does not replace the full contributor check.

The clone includes profiles, documented findings and sanitized/synthetic test
fixtures. Raw captures, screenshots, `SUMMARY.md` and `AUDIT.md` are ignored local
material and are not prerequisites. A historical capture filename is provenance,
not a downloadable fixture. Ask for separately supplied, sanitized evidence only
when a proposed protocol finding needs it.

## Optional WebUI dependencies

In the activated environment, from the repository root:

```sh
python3 -m pip install -r webui/requirements.txt
python3 -m pip check
python3 -c "import fastapi, uvicorn"
```

This installs FastAPI and Uvicorn plus their dependencies. These checks do not
start a server. The browser uses plain JavaScript/CSS without npm dependencies.
See [webui/README.md](webui/README.md#run) for live startup; starting the server
starts its device worker. Do not use live startup as an offline smoke test.

## Choose and review a change

Use the [architecture map](docs/architecture.md) to find the owning layer and the
[public work list](docs/contributor-work.md) for bounded tasks and current limits.
The [worked example](docs/evidence-to-test.md) follows a documented capture fact
through profile metadata and a builder into an existing offline test.

Keep model-specific sizes, offsets, bounds and runtime contracts in profiles;
shared effect definitions belong in the AFX catalog. Preserve unknown bytes and
compatibility identifiers. Update the owning profile/document and affected
consumers together. Label observations, owner confirmations, synthetic fixtures
and unresolved candidates explicitly. A captured write alone does not establish
a safe runtime writer or verified restoration.

Before submitting:

```sh
python3 tools/offline_checks.py
git diff --check
git status --short
```

For prose-only changes, check referenced paths/anchors and `git diff --check`.
For executable changes, use meaningful existing regressions and add coverage
where behavior or a safety boundary changes. Stage files explicitly. Keep raw
captures, serials, account data, credentials and local handoffs out of commits.
Describe the resulting behavior, checks run and remaining evidence gaps in the
commit/PR. Preserve existing unrelated work and repository-local Git identity.

## Live work is separate

Live CLI/WebUI work needs the Orion hardware, Linux HID access (normally a udev
rule), and exactly one device controller. The offline suite grants no authority
to run hardware self-tests. Writes require an authorized, measured, bounded
read/change/verify/restore plan; preserve newer owner changes and stop on failed
verification. Classic query indices must pass `protocol.check_readback_index`:
out-of-range queries can fault the device and require a physical power cycle.
Never infer larger bounds from a nested payload count.

Vendor-UI capture tooling has a separate host/guest workflow documented in
[tools/README.md](tools/README.md) and [CAPTURING.md](CAPTURING.md). It is not
needed for onboarding. Follow [the AFX workflow](docs/orion-afx-workflow.md)
before proposing new effect contracts; capture automation and runtime controls
have different verification requirements.

## Contribution licenses

Code, CLI, WebUI and documentation use **GPL-3.0-or-later**, under [LICENSE](LICENSE).
Files in `profiles/` use **MIT**, under [profiles/LICENSE](profiles/LICENSE).
Contributions are accepted under those existing terms. Include source provenance
for reusable protocol facts and assets; do not add vendor software or firmware.
