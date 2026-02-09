# Implementation Guide - Main Branch

This guide tracks how to integrate Pink System changes into the main branch.
It is meant to be updated as we iterate. Keep notes brief and actionable.

## Scope
- Pull in selected feature branches/PRs into main.
- Validate core workflows after each merge.
- Capture any required follow-up fixes.

## Current Targets
- PR #86: Quick tools
- PR #92: Color picker
- PR #103: Naming
- PR #106: Removed AutoUV coord type

## Merge Strategy (Least Destructive)
- Keep PRs open.
- Cherry-pick commits into `main` from the PR branches.
- Resolve conflicts in working tree, commit, and continue.

## Workflow
1. Update local `main`
   - `git checkout main`
   - `git pull`
2. Cherry-pick PRs in order
   - `git fetch origin pull/86/head:pr-86`
   - `git cherry-pick main..pr-86`
   - `git fetch origin pull/92/head:pr-92`
   - `git cherry-pick main..pr-92`
   - `git fetch origin pull/103/head:pr-103`
   - `git cherry-pick main..pr-103`
   - `git fetch origin pull/106/head:pr-106`
   - `git cherry-pick main..pr-106`
3. Resolve conflicts if needed
   - `git status`
   - Fix conflicts, `git add <files>`
   - `git cherry-pick --continue`
4. Push
   - `git push origin main`

## Post-Merge Checks
- Enable addon in Blender (register/unregister works).
- Create a material, rename it, confirm:
  - Group name updates to `PS_<material>` naming.
  - Layer names update to `<material>_<suffix>`.
  - Image names update to match layer names.
  - Bake image names update with the group/material rename.
- Run `run_tests.py` if available.

## Known Implementation Notes
- Name sync is controlled by preferences: `automatic_name_syncing`.
- Material rename sync uses handlers and msgbus to catch name changes.

## Change Log
- 2026-02-10: Added guide and initial merge plan.

## Next Updates
- Add conflict notes if they occur.
- Capture any regressions and their fixes.
