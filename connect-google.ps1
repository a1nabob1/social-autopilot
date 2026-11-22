# One-time Google Business Profile connection for Social Autopilot.
# Waits for the newest client_secret*.json in your Downloads folder, then runs the sign-in.
$downloads = Join-Path $env:USERPROFILE "Downloads"
Write-Host "Waiting for the Google client file (client_secret_....json) in $downloads ..." -ForegroundColor Cyan
$start = Get-Date
while ($true) {
  $file = Get-ChildItem -Path $downloads -Filter "client_secret*.json" -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($file) { break }
  if (((Get-Date) - $start).TotalMinutes -gt 15) { Write-Host "No file found after 15 minutes."; exit 1 }
  Start-Sleep -Seconds 3
}
Write-Host "Found $($file.Name)" -ForegroundColor Green
python -m autopilot.google_connect "$($file.FullName)"
if ($LASTEXITCODE -eq 0) {
  Remove-Item $file.FullName -Force   # the client secret is now safely in GitHub; don't leave a copy in Downloads
  Write-Host "Deleted the downloaded client file from Downloads (it's saved in GitHub)." -ForegroundColor Green
}
