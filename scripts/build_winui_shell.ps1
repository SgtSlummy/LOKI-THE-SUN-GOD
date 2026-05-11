$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

& "C:\Program Files\dotnet\dotnet.exe" build .\winui\LokiOperator\LokiOperator.csproj -p:Platform=x64
