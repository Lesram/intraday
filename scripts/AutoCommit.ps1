param(
  [string]$Message = "chore: auto-commit",
  [string]$Branch = ""
)

# Stage all changes (tracked + untracked; excludes ignored files)
git add -A | Out-Null

# If nothing staged, exit quietly
$hasChanges = git diff --cached --quiet; if ($LASTEXITCODE -eq 0) { Write-Output "No changes to commit."; exit 0 }

# Commit
git commit -m $Message | Out-Null

# Optionally rebase and push to the specified branch; otherwise push to default upstream
if ($Branch) {
  try { git pull --rebase origin $Branch | Out-Null } catch {}
  try { git push origin HEAD:$Branch | Out-Null } catch {}
} else {
  try { git push | Out-Null } catch {}
}
