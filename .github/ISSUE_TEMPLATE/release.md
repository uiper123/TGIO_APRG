---
name: Release checklist
about: Track what must be in place before cutting a release tag
title: "release: vX.Y.Z"
labels: ["release"]
---

## Pre-release

- [ ] All milestone issues / PRs merged
- [ ] `main` is green on CI
- [ ] Version bumped in `pyproject.toml`
- [ ] `CHANGELOG.md` updated for the new version
- [ ] Release notes drafted (highlights, breaking changes, install steps)

## Tag & trigger

- [ ] `git tag -s vX.Y.Z -m "vX.Y.Z"`
- [ ] `git push origin vX.Y.Z`
- [ ] Watch the `release` workflow: https://github.com/uiper123/TGIO_APRG/actions/workflows/release.yml

## Post-release

- [ ] Verify artifacts on https://github.com/uiper123/TGIO_APRG/releases
- [ ] Verify `pip install remote-ssh-desktop==X.Y.Z`
- [ ] Announce (X / Telegram / Discord)
- [ ] Close the milestone
