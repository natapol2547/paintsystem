# Implementation Guide - Main Branch

This guide documents how to integrate each feature without conflicts, and what was changed beyond the original branches.

## Scope
- Merge selected PRs and UV Edit workflow.
- Capture manual edits applied after cherry-picking.
- Provide a repeatable implementation path.

## Merge Order (Least Destructive)
1. PR #86: Quick tools
2. PR #92: Color picker
3. PR #103: Naming
4. PR #106: Removed AutoUV coord type
5. PR #105: Convert to PS
6. UV Edit workflow (UV-EditWorkflow branch)

## Baseline Workflow
1. Update local main
    - git checkout main
    - git pull
2. Cherry-pick PRs in order
    - git fetch origin pull/86/head:pr-86
    - git cherry-pick main..pr-86
    - git fetch origin pull/92/head:pr-92
    - git cherry-pick main..pr-92
    - git fetch origin pull/103/head:pr-103
    - git cherry-pick main..pr-103
    - git fetch origin pull/106/head:pr-106
    - git cherry-pick main..pr-106
3. Resolve conflicts, then continue
    - git status
    - Fix conflicts, git add <files>
    - git cherry-pick --continue

## Guide Files (By PR)
- [IMPLEMENTATION_GUIDE_PR_86.md](IMPLEMENTATION_GUIDE_PR_86.md)
- [IMPLEMENTATION_GUIDE_PR_92.md](IMPLEMENTATION_GUIDE_PR_92.md)
- [IMPLEMENTATION_GUIDE_PR_103.md](IMPLEMENTATION_GUIDE_PR_103.md)
- [IMPLEMENTATION_GUIDE_PR_106.md](IMPLEMENTATION_GUIDE_PR_106.md)
- [IMPLEMENTATION_GUIDE_PR_105.md](IMPLEMENTATION_GUIDE_PR_105.md)
- [IMPLEMENTATION_GUIDE_UV_EDIT_WORKFLOW.md](IMPLEMENTATION_GUIDE_UV_EDIT_WORKFLOW.md)

## Post-Merge Checks
- Enable addon in Blender (register/unregister works).
- Rename a material and confirm group/layer/image/bake image names update.
- Run run_tests.py if available.

## Known Implementation Notes
- Name sync is controlled by preferences: `automatic_name_syncing`.
- Material rename sync uses handlers and msgbus.
- Blender extensions reload may fail if PIL binaries are locked on Windows.

## Change Log
- 2026-02-10: Added UV Edit workflow details and manual change list.
