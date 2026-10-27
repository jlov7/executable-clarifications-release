# Stability and release policy

Package 1.0.0 establishes these local developer-tool contracts. Version 1.1.0 adds the supported candidate-gap explanation below while retaining the V1 interfaces and saved formats. Version 1.2.0 adds a browser target choice for known-example contracts without changing saved artifacts or their meanings. These versions do not establish production, scientific or human-use validation.

## CLI

The installed command and python -m executable_clarifications.cli expose the flags in --help and docs/USAGE.md. --version prints the package version and exits 0. --help exits 0. Successful review commands emit one JSON object on stdout and exit 0. Invalid inputs or output paths exit 2 with a diagnostic on stderr.

Result fields retain their documented status, session, observed_examples and scope, plus operation-specific audit, suggestions, policy_impact, test_written or execution fields where applicable. Diagnostic wording and JSON whitespace are not parsing interfaces. Consumers should use named fields and tolerate additive result fields. Versioned saved records retain strict shapes and reject unknown keys.

Explicit inputs must be regular files; symlinks to regular targets are supported. Non-regular inputs are refused before reading.

All requested outputs are rendered and encoded and paths preflighted before writing. Files must be new and distinct; parent directories must exist. Validation, target, unresolved-session, conflicting-path and existing-file errors produce no new files. Files are created exclusively with POSIX mode 0600 (subject to a more restrictive umask). Catchable open, stream-construction, write and close failures attempt removal of all files created by that invocation and preserve the triggering error. Refused cleanup can leave owned files. Multi-file output is not crash-atomic, and concurrent or hostile directory changes are outside this guarantee. Outputs are never silently overwritten. Browser downloads use browser/OS permissions.

## Python API

The following documented entry points are supported throughout V1:

- core.Candidate, core.default_boundary_domain and generation.generate_candidates.
- session.Session: question, answer, export_record, from_record, examples, status and remaining_ids; session.render_contract, canonical and digest.
- policy.PolicySession: corresponding adaptive operations, undo, case_review, label_case, revision_preview, reconfirm, compare_policy and suggest_cases.
- policy.load_json, validate_policy, evaluate and suggest_cases.
- examples.ExampleSet: confirm, export_record, from_record, examples and audit.
- impact.compare_policies.
- conflicts.explain_conflict(confirmed_example_set, reviewed_policy), added in 1.1.0.

Inputs, limits and return shapes are in [usage](USAGE.md). Imports are validated before activation. Returned snapshots remain detached. Predictions never create labels. Neither blocks assertion export. The library and CLI never import the implementation target.

## Saved artifacts

| Schema | Meaning |
| --- | --- |
| executable-clarifications/integer-grid-v1 | Reviewed integer generator vocabulary |
| executable-clarifications/session-v1 | Integer specification, digest and decisions |
| executable-clarifications/policy-v1 | Typed candidates and concrete cases |
| executable-clarifications/policy-session-v1 | Adaptive custom-policy decisions |
| executable-clarifications/policy-session-v2 | Ordered answers, labels and reconfirmations |
| executable-clarifications/example-set-v1 | Ordered supplied inputs and booleans |
| executable-clarifications/example-review-v1 | Digest-bound review and confirmation |
| executable-clarifications/policy-impact-v1 | Finite comparison, witnesses and coverage |
| executable-clarifications/conflict-explanation-v1 | Computed candidate-gap report, separate from saved reviews |

Files from 0.7.0 with these schemas remain readable in V1. Existing meanings, canonical normalization, digest construction, label authority and specified limit semantics are preserved. A new artifact shape/meaning requires a new schema with explicit reader support; unsupported schemas are rejected rather than guessed.

Generated Python contracts assert exactly the recorded inputs and booleans against the explicit target. Their source formatting is not an API. UI layout and browser globals are internal. The browser accepts custom-policy/example formats and exact snapshots of its three supplied integer examples. Other integer grids remain a CLI/Python path.

Digests check consistency, not identity or intent. A finite report never supplies an expected label or universal equivalence.

`conflicts.explain_conflict` and CLI `--explain-conflict` with `--audit-policy` require confirmed examples and the exact policy field vocabulary. The report contains both digests, status `OFFERED_CANDIDATE_FITS` or `NO_OFFERED_CANDIDATE_FITS`, sorted fitting candidate IDs, `core_example_ids`, `candidate_eliminations` and `removal_witnesses`. Elimination entries identify one mismatched retained example per offered candidate. Removal entries identify a fitting candidate after one retained example is omitted from the retained subset. The deterministic deletion-minimal subset is not guaranteed to have globally minimum cardinality. `minimum_cardinality_claimed` and `labels_judged_incorrect` remain false. This computed report does not modify any saved schema, label, candidate or contract. Browser explanations additionally require separate candidate-policy/audit confirmation and disappear on example edits/imports or replacement/revocation of that audit.

## Release policy

Patch versions repair compatible defects. Minor versions can add opt-in capabilities while retaining the listed interfaces/readers. Breaking documented API/CLI changes require a major version. Security fixes explicitly describe input-validation incompatibilities. No silent migration or relabelling is allowed.

A release requires pinned lint, native source verification, isolated installed-wheel and fresh installed-sdist gates. Source, wheel (with source UI assets) and sdist run all seven HTTP Chromium suites with `--browser`. Check generated assets, Python/JavaScript records/exports, negative controls, first/repeat/error recovery, package members/hashes, README examples/links and the exact source export. Use the declared Python CI matrix. Record actual checks, skips and unrun environments separately.

Keep source/package metadata consistent, and verify licensing and provenance for distributed files. A version number or local green suite does not establish human efficacy.
