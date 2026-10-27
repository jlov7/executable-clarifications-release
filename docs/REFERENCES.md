# References and provenance

The primary predecessor is [ClarifyGPT, DOI 10.1145/3660810](https://doi.org/10.1145/3660810). It motivates behavioral consistency checking and targeted clarification. This repository is a scoped integer-predicate implementation, not a reproduction of that paper or evidence of better model results.

All bundled requirements, predicate grids, input/output tables, correct/wrong fixture implementations and browser scenarios are authored examples maintained in this repository. No third-party dataset or paper text is bundled. Candidate inputs and intended-label tables stay separate. Generated browser data is derived from the local Python Session engine and checked against a committed digest.

Runtime dependencies: none. Optional build/test tooling is pinned in requirements-release.txt. Its packages are installed from their normal distributions; they are not vendored into the source or wheel. Python and Chromium/Playwright execution remain local software checks.
