# Playbook: Cut a release

How to publish a new `hydramem` version to PyPI. Decisions behind this process:
[../DECISIONS/0006-semver-and-deprecation-policy.md](../DECISIONS/0006-semver-and-deprecation-policy.md)
and [../DECISIONS/0008-packaging-and-trusted-publishing.md](../DECISIONS/0008-packaging-and-trusted-publishing.md).
Aligned with [Scientific-Python SPEC 8](https://scientific-python.org/specs/spec-0008/).

## 0. Pre-flight

- [ ] `nox -s verify` is green on `main`.
- [ ] [../DEFINITION_OF_DONE.md](../DEFINITION_OF_DONE.md) satisfied for everything in the release.
- [ ] Public-API changes are reflected in
      [../CONTRACTS/PUBLIC_API.md](../CONTRACTS/PUBLIC_API.md) and carry deprecations where needed.

## 1. Choose the version (SemVer)

- **patch** (`0.2.0 → 0.2.1`): bug fixes only.
- **minor** (`0.2.0 → 0.3.0`): new features; pre-1.0 this may include announced breaks.
- **major** (`→ 1.0.0`): stable API promise; breaking changes require a deprecation window.

## 2. Update version + changelog

- [ ] Bump `version` in [../../pyproject.toml](../../../pyproject.toml) (single source of truth).
- [ ] Move the `## [Unreleased]` section of [../../CHANGELOG.md](../../../CHANGELOG.md)
      under the new `## [X.Y.Z] – <date>` heading; keep Keep-a-Changelog categories.
- [ ] Commit: `git commit -am "chore(release): vX.Y.Z"`.

## 3. Verify the artifacts locally

```bash
nox -s build          # uv build + twine check (sdist + wheel)
# Sanity-check the wheel ships the type marker:
python -m zipfile -l dist/hydramem-*.whl | grep -E "hydramem/py\.typed"
```

## 4. Tag and push (CI publishes)

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin main --follow-tags
```

The tagged GitHub Actions release workflow builds and publishes to PyPI via
**Trusted Publishing (OIDC)** — no API tokens. Docker images are published by
`docker-publish.yml` on the same tag.

## 5. Post-release smoke test

```bash
# In a clean environment:
uv tool install "hydramem==X.Y.Z"     # or: pipx install hydramem==X.Y.Z
hydramem --help
python -c "import hydramem; print('import OK')"
```

- [ ] Verify the release on PyPI and the GitHub Releases page.
- [ ] If something is wrong, **yank** the release on PyPI (do not delete) and ship a
      fixed patch version.

## Rollback

- PyPI releases are immutable — never force-overwrite. Yank the bad version and
  release `X.Y.(Z+1)`.
- Revert the offending commit on `main`; re-run the process from step 1.
