#!/usr/bin/env bash
#
# Build the Paint System Blender extension into a distributable .zip.
#
# The set of files that get excluded from the package (dev tooling, caches,
# __pycache__, .git, etc.) is defined by [build].paths_exclude_pattern in
# blender_manifest.toml — edit it there, not here.
#
# Usage:
#   ./scripts/build.sh                 # build into ./dist
#   ./scripts/build.sh --split-platforms --verbose   # pass extra flags through
#   BLENDER=/path/to/blender ./scripts/build.sh       # use a specific Blender
#
# Set the BLENDER environment variable if `blender` is not on your PATH,
# e.g. on Windows:
#   BLENDER="/c/Program Files/Blender Foundation/Blender 4.2/blender.exe"
#
set -euo pipefail

# Resolve project root (parent of this script's directory) regardless of cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Blender executable — override with the BLENDER env var if needed.
BLENDER="${BLENDER:-blender}"

# Output directory for the built .zip (gitignored).
OUTPUT_DIR="${PROJECT_ROOT}/dist"

if ! command -v "${BLENDER}" >/dev/null 2>&1; then
  echo "error: could not find Blender executable '${BLENDER}'." >&2
  echo "       Add Blender to your PATH, or set the BLENDER env var, e.g.:" >&2
  echo "       BLENDER=\"/c/Program Files/Blender Foundation/Blender 4.2/blender.exe\" ./scripts/build.sh" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

echo "Building Paint System extension..."
echo "  Blender : ${BLENDER}"
echo "  Source  : ${PROJECT_ROOT}"
echo "  Output  : ${OUTPUT_DIR}"
echo

"${BLENDER}" --command extension build \
  --source-dir "${PROJECT_ROOT}" \
  --output-dir "${OUTPUT_DIR}" \
  "$@"

echo
echo "Done. Package(s) written to ${OUTPUT_DIR}:"
ls -1sh "${OUTPUT_DIR}"/*.zip 2>/dev/null || true
