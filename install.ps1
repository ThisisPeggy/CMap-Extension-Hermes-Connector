$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

$repository = 'https://github.com/ThisisPeggy/hermes-browser-connector'
$pluginName = 'hermes-browser'
$gatewayStopped = $false

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Message)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

function Get-HermesHome {
    if ($env:HERMES_HOME) { return [Environment]::ExpandEnvironmentVariables($env:HERMES_HOME) }
    if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA is unavailable. Set HERMES_HOME and try again.' }
    return (Join-Path $env:LOCALAPPDATA 'hermes')
}

try {
    Get-Command hermes -ErrorAction Stop | Out-Null
    Get-Command git -ErrorAction Stop | Out-Null

    & hermes gateway stop *> $null
    $gatewayStopped = $true

    $hermesHome = Get-HermesHome
    $pluginDir = Join-Path (Join-Path $hermesHome 'plugins') $pluginName

    if (Test-Path -LiteralPath $pluginDir) {
        Write-Host 'Updating Hermes Browser Connector...'
        try {
            Get-Item -LiteralPath (Join-Path $pluginDir '.git') -Force -ErrorAction Stop | Out-Null
        } catch {
            throw @"
Windows denied access to the existing Connector:
  $pluginDir

Close programs using that folder and run this command once from PowerShell opened as Administrator:
  takeown.exe /F `"$pluginDir`" /R /D Y
  icacls.exe `"$pluginDir`" /grant `"${env:USERNAME}:(OI)(CI)F`" /T /C

Then run the install command again.
"@
        }
        Get-ChildItem -LiteralPath $pluginDir -Force -Recurse -File -ErrorAction SilentlyContinue |
            ForEach-Object { if ($_.IsReadOnly) { $_.IsReadOnly = $false } }
        Invoke-Checked { git -C $pluginDir fetch --prune origin } 'Could not download the Connector update.'
        Invoke-Checked { git -C $pluginDir checkout --force origin/main } 'Could not activate the Connector update.'
        Invoke-Checked { hermes plugins enable $pluginName --no-allow-tool-override } 'Connector update succeeded, but enabling it failed.'
    } else {
        Write-Host 'Installing Hermes Browser Connector...'
        Invoke-Checked { hermes plugins install $repository --enable } 'Connector installation failed.'
    }

    $python = Get-Command py -ErrorAction SilentlyContinue
    if ($python) {
        Invoke-Checked { py -3 (Join-Path $pluginDir 'connect.py') } 'Connector pairing failed.'
    } else {
        Invoke-Checked { python3 (Join-Path $pluginDir 'connect.py') } 'Connector pairing failed.'
    }
    Write-Host 'Hermes Browser Connector is ready.' -ForegroundColor Green
} finally {
    if ($gatewayStopped) { & hermes gateway restart }
}
