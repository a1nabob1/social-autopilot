# Saves one Facebook system-user key as a GitHub secret for a1nabob1/social-autopilot.
# Usage: .\save-token.ps1 FINEHOMELOAN   (or HOINOW)
# You paste the key at a hidden prompt; it goes straight to GitHub and is never written to disk.
param([Parameter(Mandatory = $true)][ValidateSet("FINEHOMELOAN", "HOINOW")][string]$Brand)
$repo = "a1nabob1/social-autopilot"
$secure = Read-Host "Paste the $Brand Facebook key and press Enter" -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
if ([string]::IsNullOrWhiteSpace($plain)) { Write-Host "Nothing pasted - not saved."; exit 1 }
$plain.Trim() | gh secret set "$($Brand)_FB_TOKEN" -R $repo
if ($LASTEXITCODE -eq 0) { Write-Host "Saved $($Brand)_FB_TOKEN. Tell Claude 'saved'." -ForegroundColor Green }
$plain = $null
