# Validation

Run the [README checks](../README.md) with the pinned optional tooling. The source,
wheel and source-distribution browser gates each exercise seven real HTTP
Chromium suites. Browser digests use native WebCrypto.

| Contract | Discriminating checks | Limit |
| --- | --- | --- |
| Export requires explicit confirmation of supplied examples | [Known examples](../tests/test_examples.py), [browser journey](../scripts/test_examples_browser.py) | Confirmed examples do not establish unobserved intent |
| Python and browser exports preserve exact target grammar and bytes | [Target parity](../tests/test_export_target_parity.py), [export journey](../scripts/test_export_target_browser.py) | The application never imports or executes the selected target |
| No offered candidate is explained without blaming the labels | [Conflict explanations](../tests/test_conflict_explanation.py), [browser journey](../scripts/test_conflicts_browser.py) | Deletion-minimal is not globally smallest; candidates may be incomplete |
| Catchable CLI output failures preserve the original exception | [Export integrity](../tests/test_export_integrity.py), [descriptor cleanup](../tests/test_descriptor_cleanup.py) | POSIX file permissions do not control browser downloads |

The installed-package checks verify imports outside source and run an exported
contract against separate correct and deliberately wrong implementations.
[Evaluation](EVALUATION.md) describes every browser journey and retains missed
exception examples. Tests do not establish human comprehension, accessibility
certification, complete intent discovery or productivity gains.
