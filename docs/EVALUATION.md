# Evaluation and reproduction

All cases and answer tables are authored regression fixtures. They are exposed development examples, not held-out tasks or independently labeled human data. Tests exercise software mechanics, not intent discovery or comparative productivity.

From a source archive, install and run the core checks described in README. For build and browser tooling only:

```sh
uv venv .release-scratch/tooling
uv pip install --python .release-scratch/tooling/bin/python -r requirements-release.txt -r requirements-lint.txt
.release-scratch/tooling/bin/ruff check --no-cache src scripts tests
uv pip install --python .release-scratch/tooling/bin/python .
.release-scratch/tooling/bin/python -m unittest discover -s tests -v
.release-scratch/tooling/bin/python scripts/build_session_demo.py --check
node --check web/app.js
node --check web/session-app.js
node --check web/policy-engine.js
node tests/web-smoke.js
uv build --out-dir .release-scratch/dist
.release-scratch/tooling/bin/python scripts/verify_package.py .release-scratch/dist/executable_clarifications-1.2.0-py3-none-any.whl --browser
.release-scratch/tooling/bin/python scripts/verify_sdist.py .release-scratch/dist/executable_clarifications-1.2.0.tar.gz --browser
```

The package gate uses uv to create its own temporary environment, installs the supplied wheel with no dependencies, checks the installed import location, and invokes the installed command outside the checkout. The exact same exported contract must pass against the packaged reviewed correct fixture and fail against the deliberately wrong fixture. Neither must block export. Temporary package environments are removed. The gate prints artifact/contract hashes and expected exit codes.

Question IDs, specification digests and exported source are deterministic for the same grid, answers and target. Test timing, temporary paths, package timestamps and resulting archive hashes can differ across executions; receipts identify each exact artifact.

Extract the sdist into a clean directory, install it with uv, and repeat the core checks and authored example there. It contains public docs, tests, separate fixture tables, scripts and digest-verified browser assets. The wheel includes CLI/API resources and fixture implementation code; the browser launcher remains a source demo. No source fallback is used by the installed command.

`verify_sdist.py` automates the clean extraction/install and repeats all core, asset, authored-example and Node checks. Add `--browser` with CHROMIUM_PATH set to repeat the HTTP browser gate from that extraction. It removes its own extraction and environment afterward.

With a trusted already installed Chromium binary, run the actual HTTP browser gate:

```sh
CHROMIUM_PATH=/absolute/path/to/trusted/chromium \
  BROWSER_TEST_MODE=http \
  .release-scratch/tooling/bin/python scripts/test_session_browser.py
```

Playwright is pinned to 1.57.0. Do not infer HTTP coverage from the optional inline mode. The HTTP gate serves literal loopback, blocks external requests, checks three adaptive paths, identical downloaded exports, neither, readable comparisons, keyboard transition focus/descriptions/live status, and adaptive paths at 1280x900 and 390x844. It closes its browser and server. Screenshots can be retained using BROWSER_EVIDENCE_DIR. These checks are Chromium automation, not a human or screen-reader study.

The simplest contrast is a contract-free demonstration: the old `core.render_test` reconstructs a Candidate and cannot fail because a separate implementation regresses. The session export calls that separate implementation and catches the wrong boundary fixture. This demonstrates a useful regression boundary, not superiority to prose clarification or ClarifyGPT.

Negative outcomes remain required: an agreeing control asks no question and cannot export assertions; neither blocks export; an incomplete candidate set narrows after observing days=30 but misses the authored intended output at unasked days=29. These are acceptance controls, not discarded errors.

CI checks Python 3.11/3.12/3.13, package installation, browser assets and the separate browser gate. Local receipts give actual commands and counts. Record the exact source revision, runtime versions and which checks executed; a configured workflow is not evidence of a passing run. Live provider generation, matched-budget baselines, independent replication and human evaluations are NOT RUN.


The 0.3.0 practical gate adds custom multi-field imports, explicit local save/reload/resume, undo and neither recovery on desktop and mobile. It rejects altered inputs, altered history, malformed JSON, duplicate keys, unknown data and XSS-like categorical strings without replacing the active session. `test_policy_parity.py` requires Node and compares Python/browser semantics and exact contract bytes. The same custom contract passes a separately authored refund implementation and fails deliberately wrong AND and exclusive-boundary implementations. All fixtures remain authored; independent human intent and productivity evidence is NOT RUN.

`uv run --no-project --python .release-scratch/tooling/bin/python python scripts/verify_release.py` runs the source suite, generated-asset check, JavaScript syntax checks and Node smoke. Add `--browser` with a trusted existing CHROMIUM_PATH for the actual HTTP gate. Package verification remains explicit with the two archive paths above. No browser installation occurs in this script.


The 0.3.0 gate adds `scripts/test_add21_browser.py` to source and fresh-sdist browser checks. It builds the access task through typed controls without JSON editing on desktop and mobile, explicitly labels the previously unasked trainee exception, checks v2 save/resume and byte-identical Python/JS contracts, revises a grouped rule, preserves the original and requires fresh/reconfirmed answers. A second support task exercises enum membership and structurally shared comparisons. `tests/test_review.py` runs the exported omission contract against separate incomplete and exception-aware functions. These remain agent-operated authored tasks; nontechnical completion and human intent validation are NOT RUN.

The browser CI job runs all seven HTTP suites against Playwright's installed Chromium. Local runs can select an existing trusted executable with CHROMIUM_PATH. The web syntax job also checks the typed editor module.

Version 0.4.0 adds deterministic, unlabeled boundary/exception case suggestions and `scripts/test_suggestions_browser.py` to source and fresh-sdist browser gates. After the initial answer leaves one candidate, the authored loan task generates a lower-score accommodation input that both candidates reject. Only an explicit reviewed true label makes it an assertion. The same exported contract rejects a separately authored omitted-accommodation function and accepts an exception-aware function. The desktop/mobile journey checks keyboard preview/apply, an unchanged original session, empty new-digest revision, explicit reconfirmation, local save/reload and exact Python/JavaScript contract bytes. Tests also compare truncation at the attempt, case and byte limits and portable integer endpoints. Browser server lifecycle records can be retained with BROWSER_EVIDENCE_DIR.

The strong simple baseline remains a manually authored case table and unittest. Suggestions reduce typing of input objects in the authored workflow; they can create extra review work and omit three-field combinations that a manual table covers. No human productivity or superior coverage result follows. Candidate agreement, including after the last question, still does not label any generated case.

Version 0.4.1 corrects the browser outcome when explicit labels reject every candidate: it says no rule matches the recorded examples and preserves observed-example export. The suggestion browser gate checks that state on desktop and mobile. A fresh authored support-escalation trial retained a negative result: bounded suggestions missed an enterprise outage/afterhours interaction that an independent direct case table covered. Human usefulness and complete intent discovery remain NOT RUN.

Version 0.5.0 enumerates finite Cartesian grids within the existing attempt, case and byte bounds, including three-or-more-field interactions. Larger grids retain seed single/pair priority and report exact omitted combinations. Python/JavaScript regressions cover duplicate seed inputs, a complete grid at the case cap, maximum enum cardinality and safe integer endpoints. Finite-domain completeness is an input-enumeration property, not intent verification. The retained 0.4.1 missed-exception result remains historical evidence.


The 0.6.0 source and fresh-sdist `--browser` gates also run `scripts/test_examples_browser.py`. It authors/imports the same five supplied cases at 1280 and 390 pixels, checks pending export refusal, explicit confirmation, exact Python/JavaScript record and contract parity, saved review resume, typed edits, malformed/tampered import recovery, cancel/original preservation and immutable fit/no-match candidate audits. The current package CI job runs all seven browser suites against source, wheel and fresh sdist. These are authored agent-operated software checks, not independent human usability evidence.

Version 0.6.2 adds returned-artifact mutation and replay regressions in Python and JavaScript. The existing typed-policy browser suite also checks earlier/middle row deletion followed by addition, imported sparse/colliding IDs, preserved surviving rows and valid activation at both widths. A 16-row revision display checks one fresh case review per render, unchanged pending controls and explicit reconfirmation with exact contract bytes. This is an operation-count regression, not a latency or human-time result.

Version 0.7.0 adds finite policy-change comparisons in Python, JavaScript and the CLI. The typed-policy browser suite checks impact previews, preservation of the original review, fresh confirmation after a revision, and incompatible fields named like JavaScript builtins at both widths. Coverage counts describe the disclosed finite grid, including omitted combinations and witnesses. Generated witnesses carry no inferred labels; these checks establish neither universal policy equivalence nor intended behavior.

Version 1.0.0 adds scripts/test_recovery_browser.py as a fifth source/fresh-sdist HTTP suite. It checks all 30 supplied integer snapshots, exact export/undo, unsupported/tampered import recovery, actual cancelled reload/reset, focused uncommitted fields, independent save state and keyboard supplied-example onboarding at both widths. Existing browser journeys explicitly accept discard prompts during intentional reset/navigation; the recovery suite tests cancellation and preservation. Pinned Ruff checks source, scripts and tests without ignore rules. CLI preflight regressions reject invalid targets, unresolved exports and conflicting/existing paths before writing. These establish software mechanics, not human usefulness.

Version 1.1.0 adds `scripts/test_conflicts_browser.py` as the sixth HTTP suite in source, fresh-sdist and optional installed-wheel `--browser` gates. The wheel browser gate uses the isolated installed Python package with source UI assets, since the wheel remains a CLI/API package. Desktop and 390-pixel journeys require reviewed labels and a separate candidate audit, check both witness types against Python, cover a consistent alternative and stale report invalidation, and preserve exact saved reviews/contracts and independent unsaved-work warnings. `tests/test_conflict_explanation.py` compares Python/JavaScript reports for all 64 labelings of a finite six-row fixture, and retains a case where the deletion-minimal core is larger than a globally smallest core. These are authored software checks, not human comprehension evidence.

Version 1.2.0 adds `scripts/test_export_target_browser.py` as the seventh HTTP suite in all three `--browser` gates and the browser CI job. Native browser WebCrypto supplies review digests. Desktop and 390-pixel journeys check target validation, keyboard export, exact Python contract parity, reviewed correct/wrong local implementations, target changes during edit/cancel, revised examples, saved-review import and the default in a fresh tab. Target selection never supplies labels or changes review identity. These remain authored software checks; human usefulness and productivity are NOT RUN.
