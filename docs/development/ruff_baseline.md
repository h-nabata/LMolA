# Ruff CI baseline

LMolA's required Ruff baseline is the explicit `E4`, `E7`, `E9`, and `F` rule
selection in `pyproject.toml`. This is Ruff's historical default lint selection.
Changing that selection is a deliberate lint-policy change and should be reviewed
separately from feature work.

CI installs Ruff through the `dev` optional dependency. Ruff is pinned there (and
in the equivalent `all` extra) so a fresh CI environment and a developer
environment resolve the same linter implementation. Update both pins together
after checking the repository with the candidate version.

## 2026 baseline investigation

Before this policy was recorded, the dependency constraint was `ruff>=0.5` and
the Ruff configuration set only `line-length`. Therefore CI delegated both the
installed version and the implicit rule selection to whatever release pip chose
on the day of installation. A persistent Cloud environment could retain an older
already-installed Ruff while a fresh GitHub Actions environment resolved a newer
release, making their results incomparable.

The checkout at PR #119 (`eadab55`) has this same open-ended dependency and
implicit configuration. It therefore predates PR #120 and is not attributable to
Phase 18.0. No committed lock file or CI log records the exact Ruff version used
by the earlier passing Cloud verification, so that version cannot be recovered
from the repository.

The repair intentionally does not bulk-fix or refactor Python. It preserves the
previously passing historical default rule families and makes them explicit,
while pinning the verified Ruff implementation. Additional rule families should
be adopted incrementally in dedicated lint-debt changes, with their findings
reviewed rather than fixed blindly.

To inspect the baseline locally, run:

```bash
ruff --version
ruff check . --show-settings
ruff check .
```
