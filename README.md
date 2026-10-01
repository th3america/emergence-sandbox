# Emergence Sandbox

Design specification: [functional Lego assembly and AGI principles review](PLANNED-UPGRADE.md). [Recorded state](upgrade-state.json): assembly workspace implemented; synthesis uses explicit conversation handoff.

A local experiment workbench built by Ember with Greyfoot, under Sparkitect Jason's direction.

Adapting it to another operating system, runtime, storage layer, or AI bridge?
Start with [PORTING.md](PORTING.md) and the machine-readable
[`portability.json`](portability.json).
The shared conversion method lives in
[Sparkitecture001](https://github.com/th3america/Sparkitecture001/blob/main/CONVERSION-GUIDE.md).

Open http://127.0.0.1:8774/ while the server is running. For later sessions use `Open Emergence Sandbox.cmd`, or run `python app.py --port 8774` with Python 3.10+. The launcher uses the installed bundled Python and does not change execution policy. No third-party packages are needed.

## Experiment loop

1. Choose a goal and condition, or supply a custom goal, left/right JSON inputs, and independently checked expected result.
2. Prepare an AI packet. Send it through your chosen authorized conversation route. The packet omits the evaluator answer.
3. Paste the AI's JSON proposal, retaining participant attribution and any optional configuration/source fields. Record which pilot, rig, model and attachments were actually used; labels alone do not verify those configurations.
4. Run the method; inspect output, fixture verdict, and trace. Change one dependency or goal and run again.
5. Compare saved receipts in the Receipts tab. Greyfoot's evaluator distinguishes replay, changed conditions, changed goals and counterchecks, and proposes a discriminating next experiment.
6. Promote a passing recipe to a reusable tool. Compose it into another method and test again. Promotion records only the fixture on which it passed.

The local definitions treat creation as synthesis resolving a result. That result becomes another future ingredient. Self-prompting (generating intermediate demands), method creation and self-governance are separately reviewed; a passing recipe alone does not establish all three. Prior methods and failed routes can be imported as proposals with source notes and retested. The integrated pilot/rig/model/accessory metaphor describes configuration, not automatic portability.

## Actual execution contract

Six operations: normalize, sort, fingerprint, compare, select, use_tool. Recipes contain ordered steps and references to previous outputs or $left/$right. normalize rejects contradictory aliases. sort uses canonical-JSON lexical ordering (not numeric ordering). compare requires unique nonempty string ids. JSON equality preserves type distinctions. Tools use pinned recipe digests. Custom expected results are researcher-supplied equality oracles.

Limits: 24 steps per recipe, 128 shared steps across nested tools, nesting 3, 200 record rows, 32K-character recipe and 100K-character intermediate values. HTTP requests are limited to 100KB. No arbitrary code, network or filesystem operation is exposed inside recipes. This is a bounded recipe interpreter, not an operating-system isolation boundary. Loopback Host/Origin/token checks do not defend against other software already running as this user.

SQLite at data/lab.sqlite retains runs, promoted tools and stop controls. API provides no edit/delete of prior records; local file access can still change the database. Digests detect content changes when verified; they are not identity signatures. A failed run currently saves the error without a partial step trace. UI lists the latest 40 runs; the database retains older records.

## API

GET /api/state supplies state and the local session token. POST requests require X-Lab-Token and JSON:

- /api/packet: goal, condition, optional custom_fixture.
- /api/run: proposal, source (external_ai/human/authored_demo), goal, condition, optional disabled, custom_fixture, parent_run.
- /api/promote: run_id, name.
- /api/compare: previous and current saved run IDs.
- /api/stop and /api/resume: empty object. Stop rejects new execution; synchronous bounded work already executing finishes first.

No outbound model service is connected automatically. Bridges carry proposals and feedback explicitly.

## Tests and provenance

Run `python -m unittest discover -v` and `node --check web/app.js`. Initial build: 24 passing tests, including four supplied by Greyfoot and four integration regressions. The UI was exercised for a four-condition suite, promotion, reuse, dependency ablation, a custom fixture, and paired comparison.

Greyfoot wrote the initial paired evaluator and its four tests, and identified malformed parameter validation. Ember wrote the interpreter/server/UI, integrated and refined the evaluator, and performed execution and vault verification. Exact peer source and surrounding messages are preserved in the receipt artifact.

## Functional assembly workspace

Start on Assembly: select or add pieces, connect relationships, state the desired creation and configuration, then prepare one synthesis packet. Send it through your chosen AI conversation and paste the returned JSON. Saving retains a conceptual artifact with contributions, generated demands, governance, conflicts and unverified claims. It becomes a compound piece for subsequent assemblies. Claims can be transferred to a custom test setup. No automatic model connection or background pulse is installed.

27 automated tests cover the integrated workspace and previous runner. Conceptual claim validation remains a researcher/AI review task; equality fixtures are one available test adapter.

## Publication boundary

The public repository contains the implementation, tests, design notes and
explicit contributor attribution. Private conversation history, vault receipts,
and the local runtime database are intentionally excluded. Manual synthesis
handoff remains the implemented boundary; conceptual creation claims require
separate tests.
