# run_tests.py
import bpy
import sys

# --- IMPORTANT ---
# Change this to the actual folder name of your addon
# (the one that contains __init__.py)
ADDON_FOLDER_NAME = "paint_system"

print(f"Attempting to enable addon: {ADDON_FOLDER_NAME}")

try:
    # Enable the addon
    bpy.ops.preferences.addon_enable(module=ADDON_FOLDER_NAME)
    print(f"Successfully enabled addon '{ADDON_FOLDER_NAME}'.")

except Exception as e:
    print(f"Error: Failed to enable addon '{ADDON_FOLDER_NAME}'.", file=sys.stderr)
    print(e, file=sys.stderr)
    sys.exit(1) # Exit with an error code to fail the CI job

# If we reach here, the addon was enabled successfully.
# You could add more sophisticated tests below, such as verifying that
# your custom operators or panels are registered.

print("Test passed.")
sys.exit(0) # Exit with success code