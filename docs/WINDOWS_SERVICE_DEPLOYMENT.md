# Windows Service Deployment and Commissioning

This runbook deploys one immutable LOKI release to Windows and registers the
bot and dashboard as separate native services. Repository tests and a verified
archive establish package readiness only. They do not prove live Discord,
dashboard OAuth, service recovery, or production-guild commissioning.

## Fixed contract

| Item | Required value |
|---|---|
| Bot service | `LokiTHESunGodBot` |
| Dashboard service | `LokiTHESunGodDashboard` |
| Bot child | `<venv>\Scripts\python.exe <release>\local_loki_runtime.py --mode full --host 127.0.0.1 --port 9101` |
| Dashboard child | `<venv>\Scripts\python.exe <release>\dashboard_app.py` |
| Stable config | `C:\ProgramData\Loki\config\lokithesungod.env` |
| Releases | `C:\ProgramData\Loki\releases\<candidate-id>` |
| Virtual environments | `C:\ProgramData\Loki\venvs\<candidate-id>` |
| Logs | `C:\ProgramData\Loki\logs\bot-service.log` and `dashboard-service.log` |
| Service identity | `LOKI\Administrator` |

Services use delayed automatic startup. SCM recovery restarts a failed child
after 60 seconds, then 120 seconds, with a 24-hour failure reset. The native
service wrapper launches no desktop UI and passes no secrets in command-line
arguments.

`LOKI\Administrator` is deliberately high privilege. Compromise of either
service can expose broad machine or domain authority plus credentials stored
for that identity. Restrict ACLs on `C:\ProgramData\Loki`, deny unnecessary
interactive/network access, monitor service changes, and rotate credentials
after suspected compromise. A dedicated least-privilege service identity is a
safer future replacement, but it is outside this commissioning contract.

## Secrets and stable config

Secret precedence is **Credential Manager > process environment > `.env`**.
Credential targets use `LOKI/LokiTHESunGod/<ENV_NAME>`. Credential values must
never appear in commands, transcripts, service registry arguments, or logs.
The stable `.env` remains a supported fallback, but Credential Manager is the
preferred permanent store.

Create the stable config with nonsecret commissioning gates before service
installation:

```powershell
$configRoot = "C:\ProgramData\Loki\config"
New-Item -ItemType Directory -Path $configRoot -Force | Out-Null
@'
LOKI_LOCAL_ALLOW_FULL=true
RELAY_ENABLED=false
LOKI_ENABLE_SLASH_SYNC=false
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=5000
TEST_GUILD_ID=<test-guild-id>
DISCORD_CLIENT_ID=<application-id>
REDIRECT_URI=http://127.0.0.1:5000/callback
DASHBOARD_PUBLIC_URL=http://127.0.0.1:5000
'@ | Set-Content -LiteralPath "$configRoot\lokithesungod.env" -Encoding UTF8
```

Keep `RELAY_ENABLED=false` and `LOKI_ENABLE_SLASH_SYNC=false` throughout
initial acceptance. Do not add a production guild ID.

## 1. Build and transfer an immutable candidate

Run from the clean isolated source worktree on the build PC:

```powershell
if (git status --porcelain) { throw "Source tree must be clean." }
& .\scripts\prepare_loki_server_bundle.ps1
$buildArchive = "<archive path printed by prepare_loki_server_bundle.ps1>"
$trustedArchiveSha256 = (Get-FileHash -LiteralPath $buildArchive -Algorithm SHA256).Hash.ToLowerInvariant()
$trustedArchiveSha256
```

The command creates `handoff\<candidate-id>.zip`, its JSON SHA-256 sidecar,
and a portable `.sha256` digest. Transfer all three files through the existing
SSH alias with strict host-key checking enabled:

```powershell
ssh -o StrictHostKeyChecking=yes loki 'powershell -NoProfile -Command "New-Item -ItemType Directory -Force C:\ProgramData\Loki\incoming | Out-Null"'
scp -o StrictHostKeyChecking=yes $buildArchive "$buildArchive.sha256.json" "$buildArchive.sha256" 'loki:C:/ProgramData/Loki/incoming/'
```

Never accept a changed or unknown host key during release transfer.

Record the 64-character `$trustedArchiveSha256` value through the operator's
trusted channel. On Loki, paste that build-PC value and independently compare
it with the transferred archive before extraction. Do not derive the trusted
value from a sidecar or `.sha256` file transferred beside the archive.

```powershell
$archive = "C:\ProgramData\Loki\incoming\<candidate-id>.zip"
$expectedHash = "<64-character SHA-256 recorded on the build PC>".ToLowerInvariant()
if ($expectedHash -notmatch '^[0-9a-f]{64}$') { throw "Trusted archive SHA-256 is invalid." }
$actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -cne $expectedHash) { throw "Transferred archive SHA-256 mismatch." }

$sidecar = "$archive.sha256.json"
$candidateId = "<candidate ID printed on the build PC>"
if ($candidateId -notmatch '^loki-[0-9a-f]{12}$') { throw "Trusted candidate ID is invalid." }
$releaseRoot = "C:\ProgramData\Loki\releases\$candidateId"
if (Test-Path -LiteralPath $releaseRoot) { throw "Release directory already exists: $releaseRoot" }
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $releaseRoot
```

Retain the archive, sidecars, release directory, and previous releases. Do not
overwrite a release directory or delete an old virtual environment during the
first repair.

## 2. Prepare Python 3.12 before credential seeding

Open an elevated PowerShell session as exact identity `LOKI\Administrator`.
Confirm the identity before continuing:

```powershell
[Security.Principal.WindowsIdentity]::GetCurrent().Name
```

Build and verify the candidate-specific Python 3.12 environment first. This
order lets the credential helper re-execute inside the verified environment
where pywin32 is installed.

```powershell
$venvPath = "C:\ProgramData\Loki\venvs\$candidateId"
$verificationRoot = "C:\ProgramData\Loki\verification\$candidateId"
& "$releaseRoot\scripts\install_loki_local.ps1" `
  -VenvPath $venvPath `
  -VerificationRoot $verificationRoot
```

The installer runs dependency installation, pywin32 imports, compile, Ruff,
secret scan, preflight, release checks, and repository tests. It does not start
Discord or register a service.

## 3. Seed Credential Manager

Still running as `LOKI\Administrator`, enter each value interactively:

```powershell
Push-Location $releaseRoot
try {
  py -3.12 scripts\set_loki_credentials.py set DISCORD_TOKEN
  py -3.12 scripts\set_loki_credentials.py set DISCORD_CLIENT_SECRET
  py -3.12 scripts\set_loki_credentials.py set DASHBOARD_SECRET_KEY
} finally {
  Pop-Location
}
```

Add other allowlisted secrets only when the corresponding integration is
approved. The helper confirms values without echoing them and rejects any
identity other than `LOKI\Administrator`.

## 4. Install services, then start in order

Installation revalidates the archive, extracted manifest, Python version,
stable config, and tests. It prompts interactively for the exact service logon
credential and leaves both services stopped.

```powershell
& "$releaseRoot\scripts\install_loki_services.ps1" `
  -ReleaseRoot $releaseRoot `
  -VenvPath $venvPath `
  -ArchivePath $archive `
  -SidecarPath $sidecar `
  -ExpectedArchiveSha256 $expectedHash

Start-Service LokiTHESunGodBot
Start-Sleep -Seconds 5
Invoke-WebRequest http://127.0.0.1:9101/healthz -UseBasicParsing
Start-Service LokiTHESunGodDashboard
Invoke-WebRequest http://127.0.0.1:5000/healthz -UseBasicParsing
```

Bot health must remain non-200 until Discord reports ready. If bot readiness
does not converge, stop commissioning and inspect redacted service logs; do not
enable relay, slash sync, or another bot process to compensate.

## 5. Verify machine evidence

Run the verifier as exact identity `LOKI\Administrator`, because the log scan
must read the same user's Credential Manager entries:

```powershell
& "$releaseRoot\scripts\verify_loki_services.ps1" `
  -ReleaseRoot $releaseRoot `
  -VenvPath $venvPath
```

Required evidence:

- both services report `Running`, delayed automatic startup, exact
  `LOKI\Administrator` identity, and configured SCM recovery;
- exactly one child exists per service, under its SCM wrapper, using Python
  `3.12.x` from the active versioned virtual environment;
- bot `http://127.0.0.1:9101/healthz` returns HTTP 200 with Discord connected,
  ready, and a ready state;
- dashboard `http://127.0.0.1:5000/healthz` returns HTTP 200;
- active release manifest still verifies, rollback evidence exists, and logs
  contain no known credential value or OAuth token pattern.

Recovery testing force-terminates each child and is therefore a separate,
explicit operator action:

```powershell
& "$releaseRoot\scripts\verify_loki_services.ps1" `
  -ReleaseRoot $releaseRoot `
  -VenvPath $venvPath `
  -ExerciseRecovery `
  -RecoveryConfirmation "EXERCISE LOKI SERVICE RECOVERY"
```

Do not combine recovery exercise with first login or Discord command testing.

## 6. Human-only Discord and dashboard acceptance

Before any live command, confirm these privileged intents in the Discord
Developer Portal:

- `MESSAGE_CONTENT`
- `GUILD_MEMBERS`

Then, only in the configured test guild:

1. Complete dashboard OAuth login at `http://127.0.0.1:5000` and confirm the
   expected test guild is visible.
2. Run one bounded, non-mutating command that is known to be enabled.
3. Confirm a normal member is denied an administrator-only action, then confirm
   the authorized test operator can use the same bounded action.
4. Re-run machine verification and inspect logs without copying credential
   values into evidence.

Initial acceptance does not authorize relay, automatic slash-command sync,
production-guild mutation, production messages, or a reboot. Each requires
separate operator approval. Do not claim production commissioning until those
checks are explicitly authorized and observed.

## Upgrade

Build, transfer, hash-check, extract, and prepare each new candidate into new
release and virtual-environment directories. Seed new or rotated credentials
before switching. Then stop both services and update their release binding:

```powershell
Stop-Service LokiTHESunGodDashboard
Stop-Service LokiTHESunGodBot
& "$newReleaseRoot\scripts\install_loki_services.ps1" `
  -ReleaseRoot $newReleaseRoot `
  -VenvPath $newVenvPath `
  -ArchivePath $newArchive `
  -SidecarPath $newSidecar `
  -ExpectedArchiveSha256 $newExpectedArchiveSha256 `
  -PreserveExistingIdentity
Start-Service LokiTHESunGodBot
Start-Service LokiTHESunGodDashboard
& "$newReleaseRoot\scripts\verify_loki_services.ps1" `
  -ReleaseRoot $newReleaseRoot `
  -VenvPath $newVenvPath
```

Do not remove the previous archive, release, venv, or rollback JSON until the
new candidate completes the approved acceptance window.

## Rollback

Rollback rebinds both stopped services to the previous immutable release and
venv. It does not delete the failed candidate.

```powershell
Stop-Service LokiTHESunGodDashboard
Stop-Service LokiTHESunGodBot
& "$previousReleaseRoot\scripts\install_loki_services.ps1" `
  -ReleaseRoot $previousReleaseRoot `
  -VenvPath $previousVenvPath `
  -ArchivePath $previousArchive `
  -SidecarPath $previousSidecar `
  -ExpectedArchiveSha256 $previousExpectedArchiveSha256 `
  -PreserveExistingIdentity
Start-Service LokiTHESunGodBot
Start-Service LokiTHESunGodDashboard
& "$previousReleaseRoot\scripts\verify_loki_services.ps1" `
  -ReleaseRoot $previousReleaseRoot `
  -VenvPath $previousVenvPath
```

Record the failed candidate ID and retained rollback-evidence path. Investigate
in place; do not edit bytes inside either immutable release.

## References

- [pywin32 native Windows service framework](https://github.com/mhammond/pywin32)
- [Microsoft guidelines for services](https://learn.microsoft.com/en-us/windows/win32/rstmgr/guidelines-for-services)
