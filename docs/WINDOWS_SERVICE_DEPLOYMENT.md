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
| Trusted Python launcher | `C:\Windows\py.exe`, all-users install, Python 3.12 available |
| Trusted Python runtime | `C:\Program Files\Python312\python.exe`, machine-wide Python 3.12 |
| Trusted Git | `C:\Program Files\Git\cmd\git.exe`, machine-wide Git for Windows |

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

Run every Loki-side provisioning block below from one elevated, profile-free
Windows PowerShell 5.1 session as exact identity `LOKI\Administrator`. Start it
as `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile`. If a
new session is opened, redefine the `Set-LokiExactAcl` and
`Get-LokiFileSha256` helpers before use.

Before any provisioning command, fail closed unless the current process is the
canonical Windows PowerShell 5.1 host. This check uses only .NET state; it does
not resolve a host through PATH or import a PowerShell module:

```powershell
$expectedPowerShell = [IO.Path]::GetFullPath(
  "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
)
$actualPowerShell = [IO.Path]::GetFullPath(
  [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
)
$actualPsHome = [IO.Path]::GetFullPath($PSHOME).TrimEnd('\')
$expectedPsHome = [IO.Path]::GetDirectoryName($expectedPowerShell).TrimEnd('\')
if ($actualPowerShell -ine $expectedPowerShell -or $actualPsHome -ine $expectedPsHome) {
  throw "Provisioning requires the canonical Windows PowerShell 5.1 host."
}
if ($PSVersionTable.PSEdition -cne "Desktop" -or
    $PSVersionTable.PSVersion.Major -ne 5 -or
    $PSVersionTable.PSVersion.Minor -ne 1) {
  throw "Provisioning requires Windows PowerShell Desktop 5.1."
}
if ([Security.Principal.WindowsIdentity]::GetCurrent().Name -ine "LOKI\Administrator") {
  throw "Provisioning requires exact identity LOKI\Administrator."
}
$env:PSModulePath = [IO.Path]::Combine($expectedPsHome, "Modules")
```

For a fresh commissioning, create the LOKI root and stable config with exact
ACLs before transfer. Do not harden an old user-writable tree in place: DACL
changes do not revoke retained write handles. If `C:\ProgramData\Loki` already
exists but is not a previously verified commissioned tree, stop here and use
the unsupported-legacy retirement gate below to preserve and quarantine it.

```powershell
$lokiRoot = "C:\ProgramData\Loki"
$configRoot = "$lokiRoot\config"
$configPath = "$configRoot\lokithesungod.env"
if ([IO.Directory]::Exists($lokiRoot) -or [IO.File]::Exists($lokiRoot)) {
  throw "Existing LOKI root requires exact commissioned-state verification; do not bless it in place."
}
if ([IO.File]::GetAttributes("C:\ProgramData") -band [IO.FileAttributes]::ReparsePoint) {
  throw "C:\ProgramData must not be a reparse point."
}

function New-LokiExactSecurity {
  param([switch]$Directory)
  $admins = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
  $system = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
  $acl = if ($Directory) { New-Object Security.AccessControl.DirectorySecurity } else { New-Object Security.AccessControl.FileSecurity }
  $acl.SetAccessRuleProtection($true, $false)
  $acl.SetOwner($admins)
  $inheritance = if ($Directory) {
    [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
  } else { [Security.AccessControl.InheritanceFlags]::None }
  foreach ($sid in @($system, $admins)) {
    $rule = New-Object Security.AccessControl.FileSystemAccessRule(
      $sid, [Security.AccessControl.FileSystemRights]::FullControl, $inheritance,
      [Security.AccessControl.PropagationFlags]::None, [Security.AccessControl.AccessControlType]::Allow
    )
    [void]$acl.AddAccessRule($rule)
  }
  return $acl
}

function Set-LokiExactAcl {
  param([string]$Path, [switch]$Directory)
  if ([IO.File]::GetAttributes($Path) -band [IO.FileAttributes]::ReparsePoint) { throw "LOKI path is a reparse point: $Path" }
  $acl = New-LokiExactSecurity -Directory:$Directory
  if ($Directory) { [IO.Directory]::SetAccessControl($Path, $acl) }
  else { [IO.File]::SetAccessControl($Path, $acl) }
}

function Assert-LokiExactAcl {
  param([string]$Path, [switch]$Directory)
  if ([IO.File]::GetAttributes($Path) -band [IO.FileAttributes]::ReparsePoint) { throw "LOKI path is a reparse point: $Path" }
  $acl = if ($Directory) { [IO.Directory]::GetAccessControl($Path) } else { [IO.File]::GetAccessControl($Path) }
  $admins = 'S-1-5-32-544'
  $system = 'S-1-5-18'
  if (-not $acl.AreAccessRulesProtected -or
      $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne $admins) {
    throw "LOKI path owner or inheritance protection is not exact: $Path"
  }
  $rules = @($acl.GetAccessRules($true, $false, [Security.Principal.SecurityIdentifier]))
  if ($rules.Count -ne 2) { throw "LOKI path must have exactly two explicit ACL rules: $Path" }
  $seen = @{}
  foreach ($rule in $rules) {
    $sid = [string]$rule.IdentityReference.Value
    $requiredInheritance = if ($Directory) {
      [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
    } else { [Security.AccessControl.InheritanceFlags]::None }
    if ($sid -notin @($system, $admins) -or
        $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
        $rule.FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl -or
        $rule.InheritanceFlags -ne $requiredInheritance -or
        $rule.PropagationFlags -ne [Security.AccessControl.PropagationFlags]::None) {
      throw "LOKI path ACL rule is not exact: $Path"
    }
    $seen[$sid] = $true
  }
  if (-not $seen.ContainsKey($system) -or -not $seen.ContainsKey($admins)) {
    throw "LOKI path ACL omits SYSTEM or BUILTIN Administrators: $Path"
  }
}

[void][IO.Directory]::CreateDirectory($lokiRoot, (New-LokiExactSecurity -Directory))
[void](Assert-LokiExactAcl -Path $lokiRoot -Directory)
[void][IO.Directory]::CreateDirectory($configRoot, (New-LokiExactSecurity -Directory))
[void](Assert-LokiExactAcl -Path $configRoot -Directory)
$configText = @'
LOKI_LOCAL_ALLOW_FULL=true
RELAY_ENABLED=false
LOKI_ENABLE_SLASH_SYNC=false
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=5000
TEST_GUILD_ID=<test-guild-id>
DISCORD_CLIENT_ID=<application-id>
REDIRECT_URI=http://127.0.0.1:5000/callback
DASHBOARD_PUBLIC_URL=http://127.0.0.1:5000
'@
[IO.File]::WriteAllText($configPath, $configText, (New-Object Text.UTF8Encoding($false)))
Set-LokiExactAcl -Path $configPath
[void](Assert-LokiExactAcl -Path $configPath)
```

Keep `RELAY_ENABLED=false` and `LOKI_ENABLE_SLASH_SYNC=false` throughout
initial acceptance. Do not add a production guild ID.

## 1. Build and transfer an immutable candidate

Run from the clean isolated source worktree on the build PC:

```powershell
if (git status --porcelain) { throw "Source tree must be clean." }
$buildPowerShell = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
& $buildPowerShell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\prepare_loki_server_bundle.ps1
if ($LASTEXITCODE -ne 0) { throw "Immutable bundle preparation failed." }
$buildArchive = "<archive path printed by prepare_loki_server_bundle.ps1>"
$trustedArchiveSha256 = "<archive SHA-256 printed by prepare_loki_server_bundle.ps1>"
if ($trustedArchiveSha256 -notmatch '^[0-9a-f]{64}$') { throw "Printed archive SHA-256 is invalid." }
$trustedArchiveSha256
```

The command creates `handoff\<candidate-id>.zip`, its JSON SHA-256 sidecar,
its portable `.sha256` digest, plus an external bootstrap copy and bootstrap
digest. Record both printed SHA-256 values through the operator's trusted
channel. The archive hash does not authenticate the bootstrap. Transfer all
five files through the existing
SSH alias with strict host-key checking enabled:

```powershell
ssh -o StrictHostKeyChecking=yes loki 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -Command "[void][IO.Directory]::CreateDirectory(''C:\ProgramData\Loki\incoming'')"'
scp -o StrictHostKeyChecking=yes $buildArchive "$buildArchive.sha256.json" "$buildArchive.sha256" "$buildArchive.bootstrap.ps1" "$buildArchive.bootstrap.ps1.sha256" 'loki:C:/ProgramData/Loki/incoming/'
```

Never accept a changed or unknown host key during release transfer.

On Loki, paste the two build-PC values. Do not derive either trusted value from
a sidecar or `.sha256` file transferred beside the artifacts. Provision the
external bootstrap into its fixed administrator-only path, then verify it
before execution:

```powershell
$archive = "C:\ProgramData\Loki\incoming\<candidate-id>.zip"
$expectedHash = "<64-character SHA-256 recorded on the build PC>".ToLowerInvariant()
if ($expectedHash -notmatch '^[0-9a-f]{64}$') { throw "Trusted archive SHA-256 is invalid." }
function Get-LokiFileSha256 {
  param([string]$Path)
  $stream = [IO.File]::OpenRead($Path)
  $sha = [Security.Cryptography.SHA256]::Create()
  try { [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
  finally { $sha.Dispose(); $stream.Dispose() }
}
$actualHash = Get-LokiFileSha256 -Path $archive
if ($actualHash -cne $expectedHash) { throw "Transferred archive SHA-256 mismatch." }

$sidecar = "$archive.sha256.json"
$incomingBootstrap = "$archive.bootstrap.ps1"
$expectedBootstrapHash = "<bootstrap SHA-256 recorded on the build PC>".ToLowerInvariant()
if ($expectedBootstrapHash -notmatch '^[0-9a-f]{64}$') { throw "Trusted bootstrap SHA-256 is invalid." }
$lokiRoot = "C:\ProgramData\Loki"
$bootstrapRoot = "C:\ProgramData\Loki\bootstrap"
$bootstrapPath = "$bootstrapRoot\bootstrap_loki_services.ps1"
if (-not (Test-Path -LiteralPath $bootstrapRoot)) {
  New-Item -ItemType Directory -Path $bootstrapRoot | Out-Null
  Set-LokiExactAcl -Path $bootstrapRoot -Directory
}
if (Test-Path -LiteralPath $bootstrapPath) {
  $oldBootstrapHash = Get-LokiFileSha256 -Path $bootstrapPath
  Move-Item -LiteralPath $bootstrapPath -Destination "$bootstrapRoot\bootstrap_loki_services.$oldBootstrapHash.previous.ps1"
}
Copy-Item -LiteralPath $incomingBootstrap -Destination $bootstrapPath
Set-LokiExactAcl -Path $bootstrapPath
$actualBootstrapHash = Get-LokiFileSha256 -Path $bootstrapPath
if ($actualBootstrapHash -cne $expectedBootstrapHash) { throw "External bootstrap SHA-256 mismatch." }

$candidateId = "<candidate ID printed on the build PC>"
if ($candidateId -notmatch '^loki-[0-9a-f]{12}$') { throw "Trusted candidate ID is invalid." }
$releaseRoot = "C:\ProgramData\Loki\releases\$candidateId"
$venvPath = "C:\ProgramData\Loki\venvs\$candidateId"
```

Retain the archive, sidecars, release directory, and previous releases. Do not
overwrite a release directory or delete an old virtual environment during the
first repair.

## 2. Run the trusted bootstrap

Confirm the elevated session is exact identity `LOKI\Administrator` before
continuing:

```powershell
[Security.Principal.WindowsIdentity]::GetCurrent().Name
```

The bootstrap locks and recopies the hash-bound archive, extracts the release
into a new protected staging directory, verifies it, atomically promotes it,
builds a fresh staged Python 3.12 venv, installs both services transactionally,
and leaves them stopped. It invokes the protected installer copy extracted
from the trusted archive, never a script from a pre-extracted release.

This production path fails closed unless both the all-users launcher at exact
path `C:\Windows\py.exe` and machine-wide runtime at exact path
`C:\Program Files\Python312\python.exe` exist under non-reparse, protected
system ancestry. The launcher is used only for non-executing runtime inventory;
candidate verification and venv creation invoke the exact protected runtime.
A per-user runtime, WindowsApps alias, or other PATH-resolved executable is not
accepted. Provision these prerequisites separately before this ceremony; do not
substitute another path without a new security review.
Machine-wide Git for Windows must also exist at exact path
`C:\Program Files\Git\cmd\git.exe`. The bootstrap validates and holds that
executable while the complete repository test gate runs. Production tools are
not resolved from the inherited `PATH`.

```powershell
$bootstrapScript = "C:\ProgramData\Loki\bootstrap\bootstrap_loki_services.ps1"
& $expectedPowerShell -NoProfile -ExecutionPolicy Bypass -File $bootstrapScript `
  -ArchivePath $archive `
  -SidecarPath $sidecar `
  -ExpectedArchiveSha256 $expectedHash
if ($LASTEXITCODE -ne 0) { throw "Trusted bootstrap failed." }
```

The service installer conditionally grants `SeServiceLogonRight`, validates the
interactive `LOKI\Administrator` service password without putting it in a
managed string or command line, and removes the right again if installation
fails. Release, venv, config, logs, data, cache, rollback, and verification
trees reject reparse points and are restricted to SYSTEM and Builtin
Administrators. The service registry also pins relay and slash sync off.

If either named service is classified as unsupported legacy state (wrong
account, Python 3.14, unmanaged path, secret-bearing registry environment, or
unknown recovery configuration), automatic adoption stops before SCM mutation.
Exact rollback of an unknown custom account is impossible without its old
password. Separately approve retirement of only `LokiTHESunGodBot` and
`LokiTHESunGodDashboard`, preserve system-state evidence and all old
release/venv directories, migrate secrets to Credential Manager, remove those
two legacy registrations manually, atomically rename the old
`C:\ProgramData\Loki` root to a timestamped `Loki-legacy-*` quarantine, and
rerun the fresh protected-root procedure. Never delete that quarantine during
the first repair.

## 3. Seed Credential Manager

Still running as `LOKI\Administrator`, enter each value interactively:

```powershell
$credentialPython = "$venvPath\Scripts\python.exe"
foreach ($secretName in @(
  "DISCORD_TOKEN",
  "DISCORD_CLIENT_SECRET",
  "DASHBOARD_SECRET_KEY"
)) {
  & $credentialPython -I -B `
    "$releaseRoot\scripts\set_loki_credentials.py" set $secretName
  if ($LASTEXITCODE -ne 0) {
    throw "Credential setup failed for $secretName."
  }
}
```

Add other allowlisted secrets only when the corresponding integration is
approved. The helper confirms values without echoing them and rejects any
identity other than `LOKI\Administrator`.

## 4. Start services in order

Do not reboot between bootstrap and credential seeding: services are stopped
but configured for delayed automatic startup. After credentials are stored,
start bot first and dashboard second.

```powershell
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
& $expectedPowerShell -NoProfile -ExecutionPolicy Bypass -File `
  "$releaseRoot\scripts\verify_loki_services.ps1" `
  -ReleaseRoot $releaseRoot `
  -VenvPath $venvPath
if ($LASTEXITCODE -ne 0) { throw "Service verification failed." }
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
& $expectedPowerShell -NoProfile -ExecutionPolicy Bypass -File `
  "$releaseRoot\scripts\verify_loki_services.ps1" `
  -ReleaseRoot $releaseRoot `
  -VenvPath $venvPath `
  -ExerciseRecovery `
  -RecoveryConfirmation "EXERCISE LOKI SERVICE RECOVERY"
if ($LASTEXITCODE -ne 0) { throw "SCM recovery verification failed." }
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

Build and transfer each new candidate plus its independently hash-bound
external bootstrap. Stop both services, verify/provision the bootstrap exactly
as above, and let it create fresh release and venv staging paths before updating
the service binding:

```powershell
Stop-Service LokiTHESunGodDashboard
Stop-Service LokiTHESunGodBot
& $expectedPowerShell -NoProfile -ExecutionPolicy Bypass -File $bootstrapScript `
  -ArchivePath $newArchive `
  -SidecarPath $newSidecar `
  -ExpectedArchiveSha256 $newExpectedArchiveSha256 `
  -PreserveExistingIdentity
if ($LASTEXITCODE -ne 0) { throw "Trusted upgrade bootstrap failed." }
# Seed or rotate credentials here while both services remain stopped.
Start-Service LokiTHESunGodBot
Start-Service LokiTHESunGodDashboard
& $expectedPowerShell -NoProfile -ExecutionPolicy Bypass -File `
  "$newReleaseRoot\scripts\verify_loki_services.ps1" `
  -ReleaseRoot $newReleaseRoot `
  -VenvPath $newVenvPath
if ($LASTEXITCODE -ne 0) { throw "Upgrade verification failed." }
```

Do not remove the previous archive, release, venv, or rollback JSON until the
new candidate completes the approved acceptance window.

## Rollback

Rollback is one-hop and evidence-bound. The active services' protected
`LokiInstallId` evidence must prove that both prior snapshots bind the requested
previous immutable release and venv. Arbitrary existing venv reuse is rejected,
and the failed candidate is retained.

```powershell
Stop-Service LokiTHESunGodDashboard
Stop-Service LokiTHESunGodBot
& $expectedPowerShell -NoProfile -ExecutionPolicy Bypass -File $bootstrapScript `
  -ArchivePath $previousArchive `
  -SidecarPath $previousSidecar `
  -ExpectedArchiveSha256 $previousExpectedArchiveSha256 `
  -PreserveExistingIdentity `
  -ReuseExistingVenv
if ($LASTEXITCODE -ne 0) { throw "Trusted rollback bootstrap failed." }
Start-Service LokiTHESunGodBot
Start-Service LokiTHESunGodDashboard
& $expectedPowerShell -NoProfile -ExecutionPolicy Bypass -File `
  "$previousReleaseRoot\scripts\verify_loki_services.ps1" `
  -ReleaseRoot $previousReleaseRoot `
  -VenvPath $previousVenvPath
if ($LASTEXITCODE -ne 0) { throw "Rollback verification failed." }
```

Record the failed candidate ID and retained rollback-evidence path. Investigate
in place; do not edit bytes inside either immutable release.

## References

- [pywin32 native Windows service framework](https://github.com/mhammond/pywin32)
- [Microsoft guidelines for services](https://learn.microsoft.com/en-us/windows/win32/rstmgr/guidelines-for-services)
