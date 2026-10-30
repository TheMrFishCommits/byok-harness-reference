# Run AFTER `az login` with your own account. Checks the real Azure CLI end to end: token for your API, its claims, timing, and the helper.
# usage: .\real_az_check.ps1 -Scope 'api://<apim-app-id>/.default' -Aud 'api://<apim-app-id>'
param([Parameter(Mandatory)][string]$Scope, [Parameter(Mandatory)][string]$Aud)
$sw = [Diagnostics.Stopwatch]::StartNew()
$t = & az account get-access-token --scope $Scope --query accessToken -o tsv 2>&1
$secs = [math]::Round($sw.Elapsed.TotalSeconds, 1)
if ($LASTEXITCODE -ne 0) { Write-Host "az failed in ${secs}s: $t"; exit 1 }
$jwt = ($t | Where-Object { "$_" -match '^eyJ' } | Select-Object -Last 1).Trim()
$p = $jwt.Split('.')[1].Replace('-', '+').Replace('_', '/'); while ($p.Length % 4) { $p += '=' }
$c = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($p)) | ConvertFrom-Json
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
"az latency: ${secs}s"
"aud: $($c.aud)   (expected: $Aud)  -> $(if ($c.aud -eq $Aud) {'MATCH'} else {'MISMATCH'})"
"iss: $($c.iss)"
"lifetime left: $($c.exp - $now)s"
"user: $($c.upn)$($c.preferred_username)"
"scp: $($c.scp)   roles: $($c.roles -join ',')"
