# Porting Emergence Sandbox

Use this repository as a behavioral scaffold, not as a demand to reproduce its
Windows launcher or SQLite layout exactly. Read `portability.json` before
changing an entrypoint.

## Preserve these invariants

- Recipes remain bounded and cannot execute arbitrary code, network, or
  filesystem operations.
- POST requests require the local session token and reject foreign Host/Origin
  values.
- AI synthesis remains an explicit proposal handoff; no model connection is
  implied by a label.
- Runs, promotion, comparison, stop state, provenance, and contributor
  attribution retain their current semantics.
- A passing fixture does not establish general emergence, adaptation, or
  portability.

## Replaceable adapters

| Adapter | Current implementation | Target contract |
|---|---|---|
| Python launcher | `start.ps1` or direct Python | Start `app.py`, pass port/data explicitly, surface startup failure |
| HTTP service | `ThreadingHTTPServer` on loopback | Preserve API, size limits, token, Host/Origin checks, and loopback-only exposure |
| State | SQLite file | Preserve schemas, append/history semantics, stop state, digests, and restart behavior |
| Browser opening | PowerShell `Start-Process` | Optional convenience only; never part of readiness proof |
| AI bridge | Manual packet and paste | Preserve attribution, configuration fields, unverified-claim labeling, and explicit operator action |

## Configuration

Portable direct launch:

```text
python app.py --port 8774 --data ./data/lab.sqlite
```

PowerShell launcher:

```powershell
./start.ps1 -Port 8774 -Python /path/to/python -Data /path/to/state
```

`EMERGENCE_PYTHON` may supply the interpreter. A `python` executable on `PATH`
is used next; a Codex-bundled interpreter is only a compatibility fallback.

## Target conversion

1. Record OS, architecture, Python version, browser, filesystem, and chosen
   state path.
2. Run the mechanical checks before editing.
3. Replace one adapter at a time. Add a test before changing an untested
   invariant.
4. Exercise readiness, token rejection, foreign-origin rejection, stop/resume,
   persistence across restart, promotion, and comparison.
5. Test with a fresh state directory. Do not copy `data/lab.sqlite` from another
   machine and call the target clean.
6. Record the exact commit and commands in a `PortableScaffoldConversion/1`
   receipt.

## Verification matrix

```text
python -m unittest discover -v
node --check web/app.js
python app.py --help
```

Then start the server on the target, complete one fixture run, restart it with
the same database, and confirm the saved run remains visible. Cross-platform CI
establishes only the mechanical layer; the target operational check is still
required.

## AI handoff

Tell the converting AI the target OS/runtime and require it to preserve every
invariant above. It must report target observations separately from assumptions,
identify skipped checks, and must not weaken HTTP or recipe boundaries merely
to make the application start.
