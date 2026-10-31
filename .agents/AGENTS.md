# Agent Customization Rules

1. **Conventional Commits**: Every PR title and every commit on a feature
   branch must follow the Conventional Commits specification. CI lints both
   (`scripts/lint-commits.sh`, the `conventional_commits` check): the title
   must match `type(scope): description` — e.g. `fix(tranche-2): energy data
   reflects reality` — where `type` is one of `feat|fix|docs|style|refactor|
   perf|test|build|ci|chore|revert|deps`, `scope` is optional lowercase
   (`[a-z0-9_-]+`), and `!:` marks a breaking change. release-please builds
   the changelog and version bumps from these titles, so `fix:` vs `feat:`
   matters.
