# Quick Tools (PR #86)

## Feature Notes
- Files: panels/quick_tools_panels.py
- Manual changes applied:
   - Move Quick Tools to its own sidebar tab: bl_category = "Quick Tools".
- Validation:
   - Quick Tools appears in its own tab; paint panel still works in Texture Paint.

## Detailed Change Map (Level 4)
- panels/quick_tools_panels.py
   - Set bl_category = "Quick Tools" to move the panel to its own tab.
