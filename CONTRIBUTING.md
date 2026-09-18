# Contribution guidelines

> **This is an unofficial project.** It is not affiliated with, endorsed by, or supported by
> Dimplex, Glen Dimplex Heating & Ventilation, or the Glen Dimplex Group. It works by talking
> to the private cloud API used by the official Dimplex Control app, discovered by
> reverse-engineering that app. No Dimplex code is included or redistributed.
>
> Contributions must respect that boundary: describe behaviour observed from the official
> app or from your own hardware, but do not paste decompiled Dimplex source, proprietary
> assets, or credentials into this repository.

Contributing to this project should be as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features

## Github is used for everything

Github is used to host code, to track issues and feature requests, as well as accept pull requests.

Pull requests are the best way to propose changes to the codebase.

1. Fork the repo and create your branch from `main`.
2. If you've changed something, update the documentation.
3. Make sure your code lints and is formatted. Either:
   - run `ruff check .` and `ruff format .` directly, or
   - install the local hooks once with `pip install pre-commit && pre-commit install`
     (this installs both the `pre-commit` and `pre-push` hook types). On every
     `git commit` it runs ruff, ruff-format, and the HA manifest formatter; on
     every `git push` it additionally runs **mypy** and the full **pytest** suite
     with coverage, mirroring the CI gate.
     (`custom_components/*/manifest.json` is formatted with `scripts/format_manifest.py`
     — indent 2, multi-line arrays — so release-please version bumps do not fight
     Prettier. Do not run Prettier on that file.)
     The ruff, mypy and pytest hooks all run from your active environment
     (`language: system`) rather than pre-commit's own copies, so activate the
     test venv (`uv pip install -r requirements_test.txt`) before committing —
     not just before pushing. That keeps one pin for ruff, in
     `requirements_test.txt`; a missing `ruff` fails the hook rather than
     silently skipping the check.
4. Add or update tests for your change and make sure `pytest` passes
   (`uv pip install -r requirements_test.txt && pytest`).
5. Use a [Conventional Commit](https://www.conventionalcommits.org/) PR title
   (`fix:`, `feat:`, `chore:` …) — this drives the automated changelog/release.
6. Issue that pull request!

### Required checks before merge to `main`

The `main` branch requires:

- a **pull request** (squash merge only; no force-push / branch delete)
- a green **`ci`** status check
- **signed commits** (repo-wide rule on all branches)
- resolved review conversation threads

When your PR changes the integration (`custom_components/`, `tests/`, `scripts/`,
or related CI config), CI runs **translations**, **lint**, **mypy**, **pre-commit**,
**pytest**, **HACS/hassfest**, and shell script syntax checks. The aggregate `ci`
job fails unless all of those succeed (and conventional commit titles pass on PRs).

When your PR changes documentation (`docs/`, `includes/`, `overrides/`,
`zensical.toml`, `README.md`, or a user-visible surface such as `services.yaml`),
CI runs a **docs** job: a strict `zensical build` plus
`scripts/check-docs-coverage.sh`. Docs-only PRs still skip the heavy integration
matrix.

Re-apply branch protection / rulesets with:

```bash
scripts/setup-branch-protection.sh
```

The script's `general` ruleset carries `required_signatures` but deliberately not `deletion`: a
deletion rule on `~ALL` overrides `delete_branch_on_merge`, so every merged PR left its branch
on the remote and deleting one by hand was refused. `main` is protected from deletion by its own
ruleset, which is the branch that needs it. The script prints the general ruleset's rules at the
end, so a regression shows up on the next run rather than as another pile of branches.

Release-please's PRs run as `github-actions[bot]`, which leaves their workflow runs waiting for
manual approval. That is the intended workflow here — the maintainer triggers and approves them
when the release is wanted — so there is no token configured for it.

## Any contributions you make will be under the MIT Software License

In short, when you submit code changes, your submissions are understood to be under the same [MIT License](http://choosealicense.com/licenses/mit/) that covers the project. Feel free to contact the maintainers if that's a concern.

## Report bugs using Github's [issues](../../issues)

GitHub issues are used to track public bugs.
Report a bug by [opening a new issue](../../issues/new/choose); it's that easy!

## Write bug reports with detail, background, and sample code

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can.
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

People _love_ thorough bug reports. I'm not even kidding.

## Use a Consistent Coding Style

This project uses [ruff](https://docs.astral.sh/ruff/) for Python linting and
formatting (config in `pyproject.toml`) and [prettier](https://prettier.io/) for
YAML/JSON/Markdown. The easiest way to apply everything is the `pre-commit`
settings included in this repository (see dedicated section below).

## Test your code modification

This custom component is based on [integration_blueprint template](https://github.com/custom-components/integration_blueprint).

It comes with development environment in a container, easy to launch
if you use Visual Studio Code. With this container you will have a stand alone
Home Assistant instance running and already configured with the included
[`.devcontainer/configuration.yaml`](./.devcontainer/configuration.yaml)
file.

You can use the `pre-commit` settings implemented in this repository to have
linting tool checking your contributions (see deicated section below).

You should also verify that existing [tests](./tests) are still working
and you are encouraged to add new ones.
You can run the tests using the following commands from the root folder:

```bash
# Create a virtual environment (uv recommended; plain venv works too)
uv venv --python 3.13 .venv
uv pip install --python .venv -r requirements_test.txt

# Lint & format
.venv/bin/ruff check .
.venv/bin/ruff format --check .

# Run tests with coverage
.venv/bin/python -m pytest tests
```

If any of the tests fail, make the necessary changes to the tests as part of
your changes to the integration.

## Build the documentation locally

The site at [dimplex-hass.kroper.uk](https://dimplex-hass.kroper.uk/) is built with
[Zensical](https://zensical.org/) and deployed from `main` by
[`.github/workflows/docs.yml`](./.github/workflows/docs.yml).

```bash
uv pip install --python .venv zensical

.venv/bin/zensical serve    # live reload on http://localhost:8000
.venv/bin/zensical build    # one-shot build into ./site
```

`strict = true` is set in `zensical.toml`, so `zensical build` **fails** on a broken
internal link or a missing heading anchor. CI runs the same command, so run it before
pushing documentation changes.

CI also runs:

```bash
bash scripts/check-docs-coverage.sh
```

which fails when an action in `services.yaml`, an entity `translation_key`, or an
options-flow constant exists but is not mentioned on its reference page. It only checks
that the docs are _aware_ the thing exists — correctness still needs a human.

## Validate the blueprints

The blueprints under `blueprints/automation/dimplex/` are checked in CI against Home
Assistant's own schemas — `BLUEPRINT_SCHEMA`, and then the automation platform schema
applied to the result of substituting sample inputs. Run it locally with:

```bash
.venv/bin/python scripts/check-blueprints.py
```

Adding a new blueprint input means adding a sample value to `SAMPLE_INPUTS` in that
script, or the check fails asking for one. It runs as a step in the `test` job, which
already installs Home Assistant.

Layout worth knowing:

| Path                         | Contents                                          |
| ---------------------------- | ------------------------------------------------- |
| `docs/`                      | published pages — every `.md` here becomes a page |
| `includes/glossary.md`       | abbreviation definitions appended to every page   |
| `overrides/main.html`        | theme template override (Open Graph tags)         |
| `docs/stylesheets/extra.css` | brand colours and layout tweaks                   |

`includes/` and `overrides/` sit outside `docs/` deliberately: Zensical publishes
every `.md` file in the docs root, and has no `exclude_docs` setting to opt out.

## Pre-commit

You can use the [pre-commit](https://pre-commit.com/) settings included in the
repostory to have code style and linting checks.

With `pre-commit` tool already installed,
activate the settings of the repository:

```console
$ pre-commit install
```

Now the pre-commit tests will be done every time you commit.

You can run the tests on all repository file with the command:

```console
$ pre-commit run --all-files
```

## License

By contributing, you agree that your contributions will be licensed under its MIT License.
