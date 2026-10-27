# Changelog

## 1.2.0

- Choose an explicit `module:function` target for known-example browser test exports, using the existing Python target grammar. Invalid targets block export; editing examples still requires fresh confirmation. The target stays outside saved review JSON and resets to `implementation:decide` in each new or reloaded tab.
- Add HTTP Chromium target journeys to source, installed-wheel, fresh-sdist and browser CI gates, including desktop/mobile keyboard export, edit/cancel, review import and fresh-tab reset. Labels, digests, confirmation, candidate audits, policy/integer exports and saved-artifact schemas keep their existing meanings.
- Human usefulness, productivity and live-model evaluation remain NOT RUN.

## 1.1.0

- Support `conflicts.explain_conflict` and CLI `--explain-conflict` for confirmed known examples and separately reviewed candidates. Reports include deletion-minimal implicated examples, elimination reasons and omitted-example fitting witnesses. They do not diagnose incorrect labels or claim a globally smallest subset.
- Show and download the same computed explanation in the existing browser candidate-audit workflow after explicit review. Invalidate it on example edits/imports, candidate replacement or revoked review. Existing saved reviews and assertion contracts retain their formats.
- Create CLI exports exclusively with private POSIX permissions and attempt rollback on catchable output failures, preserving the triggering error even if stream construction closed its descriptor. Crash atomicity and hostile-directory safety remain outside scope.
- Add cross-runtime witness parity and desktop/mobile browser coverage to source, installed-wheel and fresh-sdist gates. Pin workflow runners to Ubuntu 24.04 during the [announced ubuntu-latest migration](https://github.com/actions/runner-images/issues/14748).

## 1.0.0

Established the supported V1 CLI/Python interfaces, exact saved-review recovery, supplied-example onboarding, independent unsaved-work warnings and pinned lint gate. The existing versioned artifacts remain readable in 1.1.0.
