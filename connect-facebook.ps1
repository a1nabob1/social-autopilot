# Saves your Facebook/Instagram details as GitHub secrets for a1nabob1/social-autopilot.
# Each value is typed or pasted by you at a hidden prompt; nothing is written to disk.
$repo = "a1nabob1/social-autopilot"
$names = @(
  "HOINOW_FB_PAGE_ID", "HOINOW_FB_TOKEN", "HOINOW_IG_USER_ID",
  "FINEHOMELOAN_FB_PAGE_ID", "FINEHOMELOAN_FB_TOKEN", "FINEHOMELOAN_IG_USER_ID"
)
Write-Host "Paste each value and press Enter. Press Enter on an empty line to skip one." -ForegroundColor Cyan
foreach ($n in $names) {
  $secure = Read-Host "$n" -AsSecureString
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
  if ([string]::IsNullOrWhiteSpace($plain)) { Write-Host "  skipped"; continue }
  $plain.Trim() | gh secret set $n -R $repo
  if ($LASTEXITCODE -eq 0) { Write-Host "  saved" -ForegroundColor Green }
  $plain = $null
}
Write-Host "`nTesting the connections (read-only, nothing is posted)..." -ForegroundColor Cyan
gh workflow run check-connections.yml -R $repo
Write-Host "Done. Tell Claude 'saved' and it will read the test result."
