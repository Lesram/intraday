param(
  [string]$File="logs/current.log",
  [int]$Interval=60,
  [int]$MaxLines=2000,
  [string]$Branch="main"
)

while ($true) {
  if (Test-Path $File) {
    (Get-Content -Path $File -Tail $MaxLines) | Set-Content -Path $File -Encoding UTF8
    $status = git status --porcelain $File
    if ($status) {
      git add $File | Out-Null
      try { git commit -m ("auto: update logs ({0:o})" -f (Get-Date)) | Out-Null } catch {}
      try { git pull --rebase origin $Branch | Out-Null } catch {}
      try { git push origin HEAD:$Branch | Out-Null } catch {}
    }
  }
  Start-Sleep -Seconds $Interval
}
