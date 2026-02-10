# Convert to PS (PR #105)

## Feature Notes
- Files: panels/extras_panels.py, operators/utils_operators.py
- Manual changes:
   - Conflict resolved to keep Convert to PS and Sync Names in the panel.
   - Convert dialog uses a "Setup Name" field label.
- Validation:
   - Convert button appears on materials with Principled BSDF.

## Detailed Change Map (Level 4)
- panels/extras_panels.py
   - Convert to PS and Sync Names retained in the same panel.
- operators/utils_operators.py
   - Convert operator remains accessible for Principled BSDF materials.
