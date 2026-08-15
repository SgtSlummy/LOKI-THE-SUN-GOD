[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ReleaseRoot,
    [string]$VenvPath,
    [string]$ConfigPath = "C:\ProgramData\Loki\config\lokithesungod.env",
    [string]$ServiceAccount = "LOKI\Administrator",
    [string]$BotHealthUrl = "http://127.0.0.1:9101/healthz",
    [string]$DashboardHealthUrl = "http://127.0.0.1:5000/healthz",
    [switch]$ExerciseRecovery,
    [string]$RecoveryConfirmation
)

function Assert-TrustedWindowsPowerShellHost {
    $expectedHome = [System.IO.Path]::GetFullPath(
        "C:\Windows\System32\WindowsPowerShell\v1.0"
    )
    $expectedExecutable = [System.IO.Path]::Combine($expectedHome, "powershell.exe")
    if ([string]$PSVersionTable.PSEdition -cne "Desktop" -or
        $PSVersionTable.PSVersion.Major -ne 5 -or
        $PSVersionTable.PSVersion.Minor -ne 1 -or
        [System.IO.Path]::GetFullPath($PSHOME).TrimEnd("\") -ine $expectedHome) {
        throw "LOKI service tooling requires canonical Windows PowerShell 5.1."
    }
    $process = [System.Diagnostics.Process]::GetCurrentProcess()
    try {
        $actualExecutable = [System.IO.Path]::GetFullPath(
            [string]$process.MainModule.FileName
        )
    } finally {
        $process.Dispose()
    }
    if ($actualExecutable -ine $expectedExecutable) {
        throw "LOKI service tooling requires canonical host $expectedExecutable."
    }
    $arguments = [System.Environment]::GetCommandLineArgs()
    if ($arguments.Length -lt 6 -or
        -not $arguments[1].Equals("-NoProfile", [StringComparison]::OrdinalIgnoreCase) -or
        -not $arguments[2].Equals("-ExecutionPolicy", [StringComparison]::OrdinalIgnoreCase) -or
        -not $arguments[3].Equals("Bypass", [StringComparison]::OrdinalIgnoreCase) -or
        -not $arguments[4].Equals("-File", [StringComparison]::OrdinalIgnoreCase)) {
        throw "LOKI service tooling requires exact powershell.exe -NoProfile ... -File invocation."
    }
    $invokedScript = [System.IO.Path]::GetFullPath([string]$arguments[5])
    if ([string]::IsNullOrWhiteSpace($PSCommandPath) -or
        $invokedScript -ine [System.IO.Path]::GetFullPath($PSCommandPath)) {
        throw "LOKI service tooling -File target does not match its executing script path."
    }
    return $expectedHome
}

$trustedPowerShellHome = Assert-TrustedWindowsPowerShellHost
$ErrorActionPreference = "Stop"
Microsoft.PowerShell.Core\Set-StrictMode -Version 3.0
$env:PSModulePath = [System.IO.Path]::Combine($trustedPowerShellHome, "Modules")
Microsoft.PowerShell.Core\Import-Module -Name (
    Join-Path $trustedPowerShellHome "Modules\CimCmdlets\CimCmdlets.psd1"
) -Force -ErrorAction Stop
Microsoft.PowerShell.Core\Import-Module -Name (
    Join-Path $trustedPowerShellHome "Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1"
) -Force -ErrorAction Stop
$serviceNames = @("LokiTHESunGodBot", "LokiTHESunGodDashboard")
$script:trustedScPath = $null

function Assert-WindowsAdministrator {
    if ($env:OS -ne "Windows_NT") {
        throw "LOKI service verification is supported only on Windows."
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "LOKI service verification requires an elevated PowerShell session."
    }
    if ([string]$identity.Name -cne $ServiceAccount) {
        throw "Run verification as exact service identity $ServiceAccount so Credential Manager log scanning is authoritative."
    }
}

function Assert-ProtectedRollbackAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$Directory
    )
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Rollback evidence path cannot be a reparse point: $Path"
    }
    $securityModule = Join-Path $PSHOME "Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1"
    $loadedSecurityModule = Get-Module Microsoft.PowerShell.Security | Where-Object {
        [string]$_.Path -ieq $securityModule
    }
    if ($null -eq $loadedSecurityModule) {
        Import-Module -Name $securityModule -Force -ErrorAction Stop
    }
    $acl = Microsoft.PowerShell.Security\Get-Acl -LiteralPath $Path
    if (-not $acl.AreAccessRulesProtected) {
        throw "Rollback evidence ACL inherits unapproved access: $Path"
    }
    $systemSid = "S-1-5-18"
    $administratorsSid = "S-1-5-32-544"
    $ownerSid = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($ownerSid -cne $administratorsSid) {
        throw "Rollback evidence owner is not BUILTIN\Administrators: $Path"
    }
    $allowed = @{
        $systemSid = $true
        $administratorsSid = $true
    }
    $seen = @{}
    $rules = @($acl.GetAccessRules($true, $false, [Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne 2) {
        throw "Rollback evidence ACL does not contain exactly two protected rules: $Path"
    }
    foreach ($rule in $rules) {
        $sid = [string]$rule.IdentityReference.Value
        $fullControl = [Security.AccessControl.FileSystemRights]::FullControl
        if (-not $allowed.ContainsKey($sid) -or
            [string]$rule.AccessControlType -cne "Allow" -or
            [int]$rule.FileSystemRights -ne [int]$fullControl) {
            throw "Rollback evidence ACL contains an unapproved access rule: $Path"
        }
        if ($Directory) {
            $requiredInheritance = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
            if ([int]$rule.InheritanceFlags -ne [int]$requiredInheritance -or
                [string]$rule.PropagationFlags -cne "None") {
                throw "Rollback evidence directory ACL does not protect future evidence files."
            }
        } elseif ([string]$rule.InheritanceFlags -cne "None" -or
            [string]$rule.PropagationFlags -cne "None") {
            throw "Rollback evidence file ACL contains unexpected inheritance flags."
        }
        $seen[$sid] = $true
    }
    foreach ($requiredSid in @($systemSid, $administratorsSid)) {
        if (-not $seen.ContainsKey($requiredSid)) {
            throw "Rollback evidence ACL omits required protected principal: $requiredSid"
        }
    }
}

function Assert-ExactPropertyNames {
    param(
        [Parameter(Mandatory = $true)][object]$Object,
        [Parameter(Mandatory = $true)][string[]]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $actual = @($Object.PSObject.Properties.Name)
    if ($actual.Count -ne $Expected.Count) {
        throw "$Label has missing or extra fields."
    }
    foreach ($name in $Expected) {
        if ($actual -cnotcontains $name) {
            throw "$Label omits exact field $name."
        }
    }
}

function Assert-AdministratorOnlyPathAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$Directory,
        [switch]$RequireProtected
    )
    if ($RequireProtected) {
        Assert-ProtectedRollbackAcl -Path $Path -Directory:$Directory
        return
    }

    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Commissioned LOKI path cannot be a reparse point: $Path"
    }
    if ($Directory -and -not $item.PSIsContainer) {
        throw "Commissioned LOKI directory is not a directory: $Path"
    }
    if (-not $Directory -and $item.PSIsContainer) {
        throw "Commissioned LOKI file is a directory: $Path"
    }
    $securityModule = Join-Path $PSHOME "Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1"
    $loadedSecurityModule = Get-Module Microsoft.PowerShell.Security | Where-Object {
        [string]$_.Path -ieq $securityModule
    }
    if ($null -eq $loadedSecurityModule) {
        Import-Module -Name $securityModule -Force -ErrorAction Stop
    }
    $acl = Microsoft.PowerShell.Security\Get-Acl -LiteralPath $Path
    $systemSid = "S-1-5-18"
    $administratorsSid = "S-1-5-32-544"
    $serviceSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $ownerSid = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($ownerSid -notin @($systemSid, $administratorsSid, $serviceSid)) {
        throw "Commissioned LOKI path has an unapproved owner: $Path"
    }
    $allowed = @{
        $systemSid = $true
        $administratorsSid = $true
    }
    $seen = @{}
    $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne 2) {
        throw "Commissioned LOKI path ACL must contain exactly two effective rules: $Path"
    }
    foreach ($rule in $rules) {
        $sid = [string]$rule.IdentityReference.Value
        $fullControl = [Security.AccessControl.FileSystemRights]::FullControl
        if (-not $allowed.ContainsKey($sid) -or
            [string]$rule.AccessControlType -cne "Allow" -or
            [int]$rule.FileSystemRights -ne [int]$fullControl) {
            throw "Commissioned LOKI path has an unapproved effective ACL: $Path"
        }
        if ($Directory) {
            $requiredInheritance = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
            if ([int]$rule.InheritanceFlags -ne [int]$requiredInheritance -or
                [string]$rule.PropagationFlags -cne "None") {
                throw "Commissioned LOKI directory ACL does not secure future descendants: $Path"
            }
        } elseif ([string]$rule.InheritanceFlags -cne "None" -or
            [string]$rule.PropagationFlags -cne "None") {
            throw "Commissioned LOKI file ACL has unexpected inheritance flags: $Path"
        }
        $seen[$sid] = $true
    }
    foreach ($requiredSid in @($systemSid, $administratorsSid)) {
        if (-not $seen.ContainsKey($requiredSid)) {
            throw "Commissioned LOKI path ACL omits required principal $requiredSid."
        }
    }
}

function Assert-AdministratorTreeAcl {
    param([Parameter(Mandatory = $true)][string]$Root)
    $rootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
    if (-not $rootItem.PSIsContainer) {
        throw "Commissioned LOKI root is not a directory: $Root"
    }
    $pending = New-Object System.Collections.Generic.Stack[string]
    $pending.Push([System.IO.Path]::GetFullPath($Root))
    $isRoot = $true
    while ($pending.Count -ne 0) {
        $directory = $pending.Pop()
        Assert-AdministratorOnlyPathAcl -Path $directory -Directory -RequireProtected:$isRoot
        $isRoot = $false
        foreach ($child in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Commissioned LOKI tree contains a reparse point: $($child.FullName)"
            }
            if ($child.PSIsContainer) {
                $pending.Push([string]$child.FullName)
            } else {
                Assert-AdministratorOnlyPathAcl -Path ([string]$child.FullName)
            }
        }
    }
}

function Assert-StableConfig {
    param([Parameter(Mandatory = $true)][string]$Path)
    $effective = @{}
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }
        $parts = $line.Split(@("="), 2, [System.StringSplitOptions]::None)
        if ($parts.Count -ne 2) {
            continue
        }
        $name = $parts[0].Trim()
        $effective[$name] = $parts[1].Trim().Trim('"').Trim("'")
    }
    $required = @{
        "LOKI_LOCAL_ALLOW_FULL" = "true"
        "RELAY_ENABLED" = "false"
        "LOKI_ENABLE_SLASH_SYNC" = "false"
    }
    foreach ($name in $required.Keys) {
        if (-not $effective.ContainsKey($name) -or [string]$effective[$name] -cne [string]$required[$name]) {
            throw "Stable config commissioning flag failed: $name."
        }
    }
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label
    )
    & $FilePath @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Label failed with exit code $exitCode."
    }
}

function Invoke-NativeText {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $output = (& $FilePath @Arguments 2>&1 | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Label failed with exit code $exitCode."
    }
    return $output
}

function Assert-RecoveryTextExact {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Text
    )
    if ($Text -notmatch "(?im)^\s*RESET_PERIOD[^:]*:\s*86400\s*$") {
        throw "SCM recovery for $Name does not use exact 86400-second reset period."
    }
    foreach ($emptyField in @("REBOOT_MESSAGE", "COMMAND_LINE")) {
        if ($Text -notmatch "(?im)^\s*$emptyField\s*:\s*$") {
            throw "SCM recovery for $Name has a nonempty or missing $emptyField field."
        }
    }
    $pattern = "(?im)^\s*(?:FAILURE_ACTIONS\s*:\s*)?(RESTART|REBOOT|RUN COMMAND|NONE)\s*--\s*Delay\s*=\s*(\d+)\s+milliseconds\.\s*$"
    $matches = @([regex]::Matches($Text, $pattern))
    $expectedActions = @("RESTART", "RESTART", "NONE")
    $expectedDelays = @(60000, 120000, 0)
    if ($matches.Count -ne $expectedActions.Count) {
        throw "SCM recovery for $Name does not contain exactly three commissioned actions."
    }
    for ($index = 0; $index -lt $expectedActions.Count; $index += 1) {
        if ([string]$matches[$index].Groups[1].Value -cne $expectedActions[$index] -or
            [int]$matches[$index].Groups[2].Value -ne $expectedDelays[$index]) {
            throw "SCM recovery for $Name has an unexpected action or delay."
        }
    }
}

function Assert-RecoveryPolicy {
    param([Parameter(Mandatory = $true)][string]$Name)
    $recovery = Invoke-NativeText -FilePath $script:trustedScPath -Arguments @("qfailure", $Name) -Label "SCM recovery query for $Name"
    Assert-RecoveryTextExact -Name $Name -Text $recovery
    $failureFlag = Invoke-NativeText -FilePath $script:trustedScPath -Arguments @("qfailureflag", $Name) -Label "SCM failureflag query for $Name"
    if ($failureFlag -notmatch "(?im)^\s*FAILURE_ACTIONS_ON_NONCRASH_FAILURES\s*:\s*TRUE\s*$") {
        throw "SCM failureflag evidence for $Name does not enable non-crash recovery."
    }
}

function Get-ExpectedPythonClass {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Release
    )
    if ($Name -ceq "LokiTHESunGodBot") {
        return (Join-Path $Release "scripts\loki_bot_service") + ".LokiBotService"
    }
    if ($Name -ceq "LokiTHESunGodDashboard") {
        return (Join-Path $Release "scripts\loki_dashboard_service") + ".LokiDashboardService"
    }
    throw "Unknown LOKI service name."
}

function Assert-ExactPythonClass {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Actual,
        [Parameter(Mandatory = $true)][string]$Expected
    )
    $actualSeparator = $Actual.LastIndexOf(".")
    $expectedSeparator = $Expected.LastIndexOf(".")
    if ($actualSeparator -le 0 -or $expectedSeparator -le 0) {
        throw "Service $Name PythonClass is malformed."
    }
    $actualModule = $Actual.Substring(0, $actualSeparator)
    $expectedModule = $Expected.Substring(0, $expectedSeparator)
    $actualClass = $Actual.Substring($actualSeparator + 1)
    $expectedClass = $Expected.Substring($expectedSeparator + 1)
    if (-not [string]::Equals($actualModule, $expectedModule, [StringComparison]::OrdinalIgnoreCase) -or
        $actualClass -cne $expectedClass) {
        throw "Service $Name PythonClass does not exactly bind its release wrapper and class."
    }
}

function Get-ExpectedServiceEnvironment {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Release,
        [Parameter(Mandatory = $true)][string]$Config
    )
    return @(
        "LOKI_APP_ROOT=$Release",
        "LOKI_ENV_PATH=$Config",
        "LOKI_DB_PATH=$(Join-Path $env:ProgramData 'Loki\data\bot.db')",
        "PYTHONPYCACHEPREFIX=$(Join-Path $env:ProgramData "Loki\cache\$Name")",
        "LOKI_LOCAL_ALLOW_FULL=true",
        "RELAY_ENABLED=false",
        "LOKI_ENABLE_SLASH_SYNC=false"
    )
}

function Assert-ExactServiceEnvironment {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Actual,
        [Parameter(Mandatory = $true)][string[]]$Expected
    )
    if ($Actual.Count -ne $Expected.Count) {
        throw "Service $Name environment contains missing, duplicate, or extra entries."
    }
    $actualValues = @{}
    foreach ($entry in $Actual) {
        $parts = ([string]$entry).Split(@("="), 2, [System.StringSplitOptions]::None)
        if ($parts.Count -ne 2 -or [string]::IsNullOrWhiteSpace($parts[0]) -or $actualValues.ContainsKey($parts[0])) {
            throw "Service $Name environment is malformed or contains a duplicate name."
        }
        $actualValues[$parts[0]] = $parts[1]
    }
    foreach ($entry in $Expected) {
        $parts = ([string]$entry).Split(@("="), 2, [System.StringSplitOptions]::None)
        if (-not $actualValues.ContainsKey($parts[0]) -or
            -not [string]::Equals([string]$actualValues[$parts[0]], [string]$parts[1], [StringComparison]::OrdinalIgnoreCase)) {
            throw "Service $Name environment does not exactly match commissioned external paths."
        }
    }
}

function Get-ServiceInstallId {
    param([Parameter(Mandatory = $true)][string]$Name)
    $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
    $registry = Get-Item -LiteralPath $registryPath -ErrorAction Stop
    $installId = [string]$registry.GetValue("LokiInstallId", "")
    if ($installId -cnotmatch "^[0-9a-f]{32}$") {
        throw "Service $Name has no valid candidate-bound rollback install id."
    }
    return $installId
}

function Get-MatchingChildren {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$ExpectedCommand,
        [Parameter(Mandatory = $true)][uint32]$ParentPid,
        [Parameter(Mandatory = $true)][string]$PythonPath
    )
    $matches = @()
    foreach ($process in CimCmdlets\Get-CimInstance Win32_Process) {
        $command = [string]$process.CommandLine
        $scriptName = [System.IO.Path]::GetFileName($ScriptPath)
        if (-not $command -or $command.IndexOf($scriptName, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            continue
        }
        $normalized = ($command -replace '"', '').Trim()
        if ($normalized -ine $ExpectedCommand) {
            throw "A process for $([System.IO.Path]::GetFileName($ScriptPath)) has an unexpected command line; values were withheld."
        }
        if ([uint32]$process.ParentProcessId -ne $ParentPid) {
            throw "A process for $([System.IO.Path]::GetFileName($ScriptPath)) is not owned by its SCM service wrapper."
        }
        if ([string]$process.ExecutablePath -ine $PythonPath) {
            throw "A process for $([System.IO.Path]::GetFileName($ScriptPath)) uses the wrong Python executable."
        }
        $matches += $process
    }
    return @($matches)
}

function Assert-ServiceAndChild {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$ExpectedCommand,
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [Parameter(Mandatory = $true)][string]$Venv,
        [Parameter(Mandatory = $true)][string]$Release,
        [Parameter(Mandatory = $true)][string]$InstallId
    )
    $service = CimCmdlets\Get-CimInstance Win32_Service -Filter "Name='$Name'" -ErrorAction Stop
    if ([string]$service.State -cne "Running") {
        throw "Service $Name is not Running."
    }
    if ([string]$service.StartMode -cne "Auto") {
        throw "Service $Name is not configured for automatic startup."
    }
    if ([string]$service.StartName -cne $ServiceAccount) {
        throw "Service $Name does not use exact account $ServiceAccount."
    }
    $expectedServiceHost = '"' + (Join-Path $Venv "pythonservice.exe") + '"'
    if ([string]$service.PathName -ine $expectedServiceHost) {
        throw "Service $Name wrapper does not execute from the exact active release-specific venv."
    }
    $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
    $delayed = (Get-ItemProperty -LiteralPath $registryPath -Name DelayedAutoStart -ErrorAction Stop).DelayedAutoStart
    if ([int]$delayed -ne 1) {
        throw "Service $Name is not configured for delayed automatic startup."
    }
    $pythonClassKey = Get-Item -LiteralPath (Join-Path $registryPath "PythonClass") -ErrorAction Stop
    $pythonClass = [string]$pythonClassKey.GetValue("")
    $expectedPythonClass = Get-ExpectedPythonClass -Name $Name -Release $Release
    Assert-ExactPythonClass -Name $Name -Actual $pythonClass -Expected $expectedPythonClass
    $registry = Get-Item -LiteralPath $registryPath -ErrorAction Stop
    $requiredEnvironment = Get-ExpectedServiceEnvironment -Name $Name -Release $Release -Config $ConfigPath
    $actualEnvironment = @($registry.GetValue("Environment", @()))
    Assert-ExactServiceEnvironment -Name $Name -Actual $actualEnvironment -Expected $requiredEnvironment
    if ([string]$registry.GetValue("LokiInstallId", "") -cne $InstallId) {
        throw "Service $Name does not bind current rollback install evidence."
    }
    Assert-RecoveryPolicy -Name $Name
    $children = @(Get-MatchingChildren -ScriptPath $ScriptPath -ExpectedCommand $ExpectedCommand -ParentPid ([uint32]$service.ProcessId) -PythonPath $PythonPath)
    if ($children.Count -ne 1) {
        throw "Service $Name must own exactly one expected child; found $($children.Count)."
    }
    return $children[0]
}

function Invoke-HealthCheck {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Kind
    )
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15
    if ([int]$response.StatusCode -ne 200) {
        throw "$Kind health returned HTTP $($response.StatusCode), not 200."
    }
    $payload = $response.Content | ConvertFrom-Json
    if ($payload.ok -ne $true) {
        throw "$Kind health did not report ok=true."
    }
    if ($Kind -ceq "Bot") {
        if ($payload.discord.connected -ne $true -or $payload.discord.ready -ne $true -or [string]$payload.state -cne "ready") {
            throw "Bot health is HTTP 200 but Discord is not ready."
        }
    }
    return $payload
}

function Wait-ForRecoveredChild {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$ExpectedCommand,
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [Parameter(Mandatory = $true)][string]$Venv,
        [Parameter(Mandatory = $true)][string]$InstallId,
        [Parameter(Mandatory = $true)][uint32]$OldPid
    )
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 2
        try {
            $child = Assert-ServiceAndChild -Name $Name -ScriptPath $ScriptPath -ExpectedCommand $ExpectedCommand -PythonPath $PythonPath -Venv $Venv -Release $ReleaseRoot -InstallId $InstallId
            if ([uint32]$child.ProcessId -ne $OldPid) {
                return $child
            }
        } catch {
            continue
        }
    }
    throw "SCM did not recover $Name with a replacement child within 180 seconds."
}

Assert-WindowsAdministrator
$canonicalWindowsRoot = [System.IO.Path]::GetFullPath("C:\Windows").TrimEnd("\")
$windowsRoot = [System.IO.Path]::GetFullPath($env:WINDIR).TrimEnd("\")
if ($windowsRoot -ine $canonicalWindowsRoot) {
    throw "WINDIR must resolve to the canonical Windows root $canonicalWindowsRoot."
}
$script:trustedScPath = [System.IO.Path]::GetFullPath((Join-Path $windowsRoot "System32\sc.exe"))
if ($script:trustedScPath -ine "C:\Windows\System32\sc.exe" -or
    -not [System.IO.File]::Exists($script:trustedScPath) -or
    ([System.IO.File]::GetAttributes($script:trustedScPath) -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Service Controller must be exact non-reparse system executable C:\Windows\System32\sc.exe."
}
$commissionedServiceAccount = "LOKI\Administrator"
if ($ServiceAccount -cne $commissionedServiceAccount) {
    throw "ServiceAccount must be exact commissioned identity $commissionedServiceAccount."
}
$commissionedBotHealthUrl = "http://127.0.0.1:9101/healthz"
$commissionedDashboardHealthUrl = "http://127.0.0.1:5000/healthz"
if ($BotHealthUrl -cne $commissionedBotHealthUrl -or
    $DashboardHealthUrl -cne $commissionedDashboardHealthUrl) {
    throw "Health URLs must be exact commissioned loopback endpoints."
}
$ReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseRoot)
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$commissionedConfigPath = [System.IO.Path]::GetFullPath("C:\ProgramData\Loki\config\lokithesungod.env")
if ($ConfigPath -ine $commissionedConfigPath) {
    throw "ConfigPath must be the commissioned stable path $commissionedConfigPath."
}
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Stable config is missing: $ConfigPath"
}
Assert-StableConfig -Path $ConfigPath
$manifestPath = Join-Path $ReleaseRoot "release-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Active release is missing release-manifest.json."
}
$releaseManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$candidateId = [string]$releaseManifest.candidate_id
if ([string]::IsNullOrWhiteSpace($candidateId)) {
    throw "Active release manifest is missing candidate_id."
}
$releaseLeaf = [System.IO.Path]::GetFileName($ReleaseRoot.TrimEnd("\"))
$releaseBase = [System.IO.Path]::GetFullPath((Join-Path $env:ProgramData "Loki\releases")).TrimEnd("\")
$releaseParent = [System.IO.Path]::GetDirectoryName($ReleaseRoot).TrimEnd("\")
if ($releaseLeaf -cne $candidateId -or $releaseParent -ine $releaseBase) {
    throw "Active release directory does not match its candidate_id."
}
if ([string]::IsNullOrWhiteSpace($VenvPath)) {
    $VenvPath = Join-Path $env:ProgramData "Loki\venvs\$candidateId"
}
$VenvPath = [System.IO.Path]::GetFullPath($VenvPath)
$venvBase = [System.IO.Path]::GetFullPath((Join-Path $env:ProgramData "Loki\venvs")).TrimEnd("\")
$venvParent = [System.IO.Path]::GetDirectoryName($VenvPath).TrimEnd("\")
$venvLeaf = [System.IO.Path]::GetFileName($VenvPath.TrimEnd("\"))
if ($venvParent -ine $venvBase -or $venvLeaf -cne $candidateId) {
    throw "Active venv directory does not match its candidate_id."
}
$venvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Active service Python is missing: $venvPython"
}
$lokiRoot = [System.IO.Path]::GetFullPath((Join-Path $env:ProgramData "Loki"))
Assert-AdministratorTreeAcl -Root $lokiRoot
$pythonVersion = Invoke-NativeText -FilePath $venvPython -Arguments @("-I", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Service Python version check"
if (-not $pythonVersion.StartsWith("3.12.")) {
    throw "Active service Python is $pythonVersion, not 3.12.x."
}
Invoke-Native -FilePath $venvPython -Arguments @("-I", "-c", "import win32service, win32cred") -Label "Service pywin32 import check"
$manifestHelper = Join-Path $ReleaseRoot "scripts\release_manifest.py"
Invoke-Native -FilePath $venvPython -Arguments @(
    "-I", "-B", $manifestHelper, "verify-directory", "--root", $ReleaseRoot
) -Label "Live immutable release verification"

$serviceInstallIds = @()
foreach ($name in $serviceNames) {
    $serviceInstallIds += Get-ServiceInstallId -Name $name
}
if ($serviceInstallIds.Count -ne 2 -or [string]$serviceInstallIds[0] -cne [string]$serviceInstallIds[1]) {
    throw "LOKI services do not bind the same rollback install evidence."
}
$installId = [string]$serviceInstallIds[0]

$botScript = Join-Path $ReleaseRoot "local_loki_runtime.py"
$dashboardScript = Join-Path $ReleaseRoot "dashboard_app.py"
$botCommand = "$venvPython $botScript --mode full --host 127.0.0.1 --port 9101"
$dashboardCommand = "$venvPython $dashboardScript"
$botChild = Assert-ServiceAndChild -Name "LokiTHESunGodBot" -ScriptPath $botScript -ExpectedCommand $botCommand -PythonPath $venvPython -Venv $VenvPath -Release $ReleaseRoot -InstallId $installId
$dashboardChild = Assert-ServiceAndChild -Name "LokiTHESunGodDashboard" -ScriptPath $dashboardScript -ExpectedCommand $dashboardCommand -PythonPath $venvPython -Venv $VenvPath -Release $ReleaseRoot -InstallId $installId
Invoke-HealthCheck -Url $BotHealthUrl -Kind "Bot" | Out-Null
Invoke-HealthCheck -Url $DashboardHealthUrl -Kind "Dashboard" | Out-Null

$logRoot = Join-Path $env:ProgramData "Loki\logs"
$botLog = Join-Path $logRoot "bot-service.log"
$dashboardLog = Join-Path $logRoot "dashboard-service.log"
Invoke-Native -FilePath $venvPython -Arguments @(
    "-I", "-B", (Join-Path $ReleaseRoot "scripts\scan_service_logs.py"),
    "--env-path", $ConfigPath,
    $botLog, $dashboardLog
) -Label "Redacted service log scan"

$rollbackRoot = Join-Path $env:ProgramData "Loki\rollback"
$rollbackEvidencePath = Join-Path $rollbackRoot "service-config-$installId.json"
if (-not (Test-Path -LiteralPath $rollbackEvidencePath -PathType Leaf)) {
    throw "Current candidate-bound rollback service configuration evidence was not found."
}
Assert-ProtectedRollbackAcl -Path $rollbackRoot -Directory
Assert-ProtectedRollbackAcl -Path $rollbackEvidencePath
$rollbackEvidence = Get-Content -LiteralPath $rollbackEvidencePath -Raw | ConvertFrom-Json
Assert-ExactPropertyNames -Object $rollbackEvidence -Expected @(
    "schema", "status", "install_id", "captured_at_utc", "candidate_id",
    "incoming_candidate_id", "incoming_release_root", "incoming_venv_path",
    "service_logon_right_preexisting", "services", "completed_at_utc"
) -Label "Rollback evidence"
if ([string]$rollbackEvidence.schema -cne "loki-service-rollback/v2" -or
    [string]$rollbackEvidence.status -cne "installed" -or
    [string]$rollbackEvidence.install_id -cne $installId -or
    [string]$rollbackEvidence.candidate_id -cne $candidateId -or
    [string]$rollbackEvidence.incoming_candidate_id -cne $candidateId) {
    throw "Rollback evidence does not bind the active installed candidate."
}
if ($rollbackEvidence.service_logon_right_preexisting -isnot [bool]) {
    throw "Rollback evidence has invalid service-logon-right prior state."
}
if (-not [string]::Equals([string]$rollbackEvidence.incoming_release_root, $ReleaseRoot, [StringComparison]::OrdinalIgnoreCase) -or
    -not [string]::Equals([string]$rollbackEvidence.incoming_venv_path, $VenvPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Rollback evidence release or venv path does not match active services."
}
$evidenceServiceNames = @($rollbackEvidence.services | ForEach-Object { [string]$_.Name })
if ($evidenceServiceNames.Count -ne 2 -or
    $evidenceServiceNames -notcontains "LokiTHESunGodBot" -or
    $evidenceServiceNames -notcontains "LokiTHESunGodDashboard") {
    throw "Rollback evidence does not contain exact snapshots for both LOKI services."
}
foreach ($snapshot in @($rollbackEvidence.services)) {
    if ([bool]$snapshot.Exists) {
        Assert-ExactPropertyNames -Object $snapshot -Expected @(
            "Name", "Exists", "State", "StartMode", "StartName", "PathName",
            "DisplayName", "Description", "ServiceType", "ErrorControl",
            "ServiceDependencies", "RegistryValues", "PythonClass",
            "RollbackReleaseRoot", "RollbackVenvPath", "RollbackCandidateId"
        ) -Label "Rollback existing-service snapshot"
        $requiredRegistryValues = @(
            "ImagePath", "Start", "ObjectName", "Description", "DependOnService",
            "ErrorControl", "Type", "Environment", "FailureActions",
            "FailureActionsOnNonCrashFailures", "DelayedAutoStart", "LokiInstallId"
        )
        Assert-ExactPropertyNames -Object $snapshot.RegistryValues -Expected $requiredRegistryValues -Label "Rollback registry snapshot"
        foreach ($valueName in $requiredRegistryValues) {
            Assert-ExactPropertyNames -Object $snapshot.RegistryValues.$valueName -Expected @(
                "Exists", "Kind", "Value"
            ) -Label "Rollback registry value $valueName"
        }
        Assert-ExactPropertyNames -Object $snapshot.PythonClass -Expected @(
            "KeyExists", "Value"
        ) -Label "Rollback PythonClass snapshot"
        Assert-ExactPropertyNames -Object $snapshot.PythonClass.Value -Expected @(
            "Exists", "Kind", "Value"
        ) -Label "Rollback PythonClass value snapshot"
        $rollbackRelease = [System.IO.Path]::GetFullPath([string]$snapshot.RollbackReleaseRoot)
        $rollbackVenv = [System.IO.Path]::GetFullPath([string]$snapshot.RollbackVenvPath)
        $rollbackCandidate = [string]$snapshot.RollbackCandidateId
        if ([System.IO.Path]::GetFileName($rollbackRelease.TrimEnd("\")) -cne $rollbackCandidate -or
            [System.IO.Path]::GetFileName($rollbackVenv.TrimEnd("\")) -cne $rollbackCandidate) {
            throw "Rollback evidence release and venv do not bind the same previous candidate."
        }
        foreach ($requiredFile in @(
            (Join-Path $rollbackVenv "pythonservice.exe"),
            (Join-Path $rollbackVenv "Scripts\python.exe")
        )) {
            if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
                throw "Rollback evidence points to a missing retained venv artifact: $requiredFile"
            }
        }
        $rollbackManifestJson = Invoke-NativeText -FilePath $venvPython -Arguments @(
            "-I", "-B", $manifestHelper, "verify-directory", "--root", $rollbackRelease
        ) -Label "Retained rollback release verification"
        $rollbackManifest = $rollbackManifestJson | ConvertFrom-Json
        if ([string]$rollbackManifest.candidate_id -cne $rollbackCandidate) {
            throw "Retained rollback release verification returned the wrong candidate."
        }
    } else {
        Assert-ExactPropertyNames -Object $snapshot -Expected @("Name", "Exists") -Label "Rollback new-service snapshot"
    }
}

if ($ExerciseRecovery) {
    if ([string]$RecoveryConfirmation -cne "EXERCISE LOKI SERVICE RECOVERY") {
        throw "-ExerciseRecovery requires -RecoveryConfirmation 'EXERCISE LOKI SERVICE RECOVERY'."
    }
    Stop-Process -Id ([int]$botChild.ProcessId) -Force -ErrorAction Stop
    $botChild = Wait-ForRecoveredChild -Name "LokiTHESunGodBot" -ScriptPath $botScript -ExpectedCommand $botCommand -PythonPath $venvPython -Venv $VenvPath -InstallId $installId -OldPid ([uint32]$botChild.ProcessId)
    Invoke-HealthCheck -Url $BotHealthUrl -Kind "Bot" | Out-Null

    Stop-Process -Id ([int]$dashboardChild.ProcessId) -Force -ErrorAction Stop
    $dashboardChild = Wait-ForRecoveredChild -Name "LokiTHESunGodDashboard" -ScriptPath $dashboardScript -ExpectedCommand $dashboardCommand -PythonPath $venvPython -Venv $VenvPath -InstallId $installId -OldPid ([uint32]$dashboardChild.ProcessId)
    Invoke-HealthCheck -Url $DashboardHealthUrl -Kind "Dashboard" | Out-Null
    Invoke-Native -FilePath $venvPython -Arguments @(
        "-I", "-B", (Join-Path $ReleaseRoot "scripts\scan_service_logs.py"),
        "--env-path", $ConfigPath,
        $botLog, $dashboardLog
    ) -Label "Post-recovery redacted service log scan"
}

Write-Output "PASS: both LOKI services are Running with one exact Python 3.12 child each."
Write-Output "PASS: delayed automatic startup, service identity, recovery actions, failureflag, health, and redacted logs verified."
Write-Output "Active candidate: $candidateId"
Write-Output "Rollback evidence retained: $rollbackEvidencePath"
