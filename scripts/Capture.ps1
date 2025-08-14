param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Cmd)

New-Item -ItemType Directory -Force -Path logs | Out-Null
$log = "logs/current.log"
"--- SESSION START $(Get-Date -Format o) ---" | Set-Content -Path $log -Encoding UTF8

# Usage: pwsh -File scripts/Capture.ps1 -- npm run dev
& cmd /c ($Cmd -join ' ') 2>&1 |
  ForEach-Object {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $_"
    $line = $line -replace 'sk-[A-Za-z0-9]{10,}', '[REDACTED]'
    $line
  } | Tee-Object -FilePath $log -Append
