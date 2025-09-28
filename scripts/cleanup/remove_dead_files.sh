#!/bin/bash
set -euo pipefail

# Script to remove 0-byte and duplicate files from the backend
echo "Removing dead files from backend..."

# Files to delete
FILES_TO_DELETE=(
    "backend/backend/api/websockets.py"
    "backend/backend/api/routes/api_v1.py"
    "backend/backend/api/routes/features.py"
    "backend/backend/api/routes/portfolio.py"
    "backend/backend/api/routes/positions.py"
    "backend/backend/infra/database.py"
    "backend/backend/config_helpers.py"
)

DELETED_COUNT=0
DELETED_FILES=()

# Delete each file if it exists
for file in "${FILES_TO_DELETE[@]}"; do
    if [ -f "$file" ]; then
        echo "Deleting: $file"
        rm "$file"
        DELETED_FILES+=("$file")
        ((DELETED_COUNT++))
    else
        echo "File not found (already deleted?): $file"
    fi
done

# Check if backend/backend/api/routes/__init__.py should be deleted
ROUTES_INIT="backend/backend/api/routes/__init__.py"
if [ -f "$ROUTES_INIT" ]; then
    # Check if there are any import references to backend.api.routes
    if grep -r "backend\.api\.routes" backend/ --include="*.py" > /dev/null 2>&1; then
        echo "Keeping $ROUTES_INIT (found import references)"
    else
        echo "Deleting: $ROUTES_INIT (no import references found)"
        rm "$ROUTES_INIT"
        DELETED_FILES+=("$ROUTES_INIT")
        ((DELETED_COUNT++))
    fi
fi

# Remove empty directories if they exist
EMPTY_DIRS=(
    "backend/backend/api/routes"
)

for dir in "${EMPTY_DIRS[@]}"; do
    if [ -d "$dir" ] && [ -z "$(ls -A "$dir")" ]; then
        echo "Removing empty directory: $dir"
        rmdir "$dir"
    fi
done

# Print summary
echo ""
echo "=== CLEANUP SUMMARY ==="
echo "Total files deleted: $DELETED_COUNT"
if [ ${#DELETED_FILES[@]} -gt 0 ]; then
    echo "Deleted files:"
    for file in "${DELETED_FILES[@]}"; do
        echo "  - $file"
    done
else
    echo "No files were deleted (all were already missing)"
fi
echo "========================"

# Exit with success if we got here
echo "Cleanup completed successfully!"
exit 0