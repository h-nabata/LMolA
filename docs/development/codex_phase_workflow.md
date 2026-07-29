# Codex Phase Workflow

This reusable workflow applies to phase tasks independent of a specific machine or Git harness. [`AGENTS.md`](../../AGENTS.md) is authoritative whenever instructions overlap; read it and the phase specification before acting.

## 1. Prepare and inspect

1. Use the supplied repository checkout. Confirm the current branch and a clean working tree without printing or persisting private machine details.
2. Stop rather than overwrite tracked user changes. A disposable, untracked root `pr_body.md` may be removed as directed by `AGENTS.md`.
3. In Codex Cloud, use the platform-provided checkout and task branch. Do not require an upstream branch, switch to `main`, change remotes, or require `git pull`. In a local task, follow explicit branch/update instructions and repository policy.
4. Read scoped `AGENTS.md` files, the phase specification, relevant source, tests, and current documentation. Verify claims from the checkout rather than historical phase narration.
5. If needed, install editable development dependencies with `python -m pip install -e ".[dev]"`; do not change dependency declarations merely to prepare the environment.

## 2. Establish the baseline

Run the default checks listed in `AGENTS.md` when supported. Record exact environment limitations. Stop if a failure indicates a repository regression; continue only when a documented environment limitation does not compromise safe work.

## 3. Implement conservatively

- Define the goal, allowed files, non-goals, and acceptance criteria before editing.
- Keep the patch minimal, preserve public interfaces unless requested, and follow contract-first backend and artifact design.
- Do not broaden scope to fix unrelated issues. Add focused tests and concise documentation when behavior changes.
- Reinspect the implementation whenever a documentation claim is uncertain; mark provisional claims or omit them.

## 4. Privacy and verification

Review every changed and staged line for usernames, home paths, hostnames, credentials, raw environment output, transcripts, and task prompts. Use repository-relative paths or placeholders such as `<repo-root>`. Follow the Public Repository Privacy section in `AGENTS.md`.

Run phase-specific checks, default checks, `git diff --check`, a relative Markdown-link check when documentation changes, and inspect `git diff --stat`, `git diff --name-only`, and the complete diff. Confirm changed file types match scope.

## 5. Commit, PR, and checks

1. Stage only intended files and inspect the staged diff and privacy search.
2. Commit with the requested message after verification passes or limitations are documented.
3. Create a PR against the requested base with summary, files, tests, risk, privacy review, and follow-up information. Do not commit a temporary PR-body file.
4. Inspect available checks. Do not force-merge pending or failing checks; report failures and likely causes. Use auto-merge only when repository and task policy permit it.
5. If PR automation is unavailable, leave the committed branch ready and report the limitation without adding credentials or modifying remotes.

## 6. Final report

List files added, modified, moved, and deleted; major decisions; tests and exact results; environment setup or limitations; runtime/scope confirmation; privacy result; PR URL and checks; and remaining manual actions.
