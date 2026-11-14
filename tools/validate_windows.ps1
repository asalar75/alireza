<#
.SYNOPSIS
  AegisSec Enterprise - Windows 10/11 x64 validation (CPython 3.12 x64).

.DESCRIPTION
  Creates an isolated virtual environment, installs requirements-dev.txt, runs the complete
  pytest suite and compileall, and runs the PDF export checks on the local Windows file system
  (demo PDF, no-overwrite, concurrent exports from separate processes, temp-file cleanup).
  Everything is logged to validation_results\<UTC timestamp>\ (results.json, REPORT.md, logs).

  It never skips a required check silently: a step that cannot run is recorded as BLOCKED or
  NOT RUN with the reason, and the script exits non-zero unless every automated step is PASS.
  It does NOT run the GUI (see docs\WINDOWS_GUI_SMOKE_TEST.md) and does NOT validate Persian PDF,
  dependency locking or pip-audit.

.PARAMETER WorkDir
  Local folder for the temporary PDF export tests (default: %TEMP%). Must be on a local fixed drive.

.PARAMETER WheelDir
  Optional folder with pre-downloaded wheels. If given, pip runs with --no-index --find-links.

.PARAMETER OutDir
  Result folder (default: validation_results\<timestamp> under the repository).

.PARAMETER Rounds
  Rounds of the concurrent-export check (default 5).

.PARAMETER Procs
  Processes per round (default 6).

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate_windows.ps1
#>
[CmdletBinding()]
param(
    [string]$WorkDir = "",
    [string]$WheelDir = "",
    [string]$OutDir = "",
    [int]$Rounds = 5,
    [int]$Procs = 6
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

$Stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot ("validation_results\" + $Stamp) }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir = (Resolve-Path -LiteralPath $OutDir).Path

$script:Steps = New-Object System.Collections.ArrayList
$script:Commands = New-Object System.Collections.ArrayList
$script:Meta = [ordered]@{}
$script:Pytest = $null
$script:SysPy = $null
$script:VenvPy = $null
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$env:PYTHONUTF8 = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

function Write-Text([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Save-Results {
    $obj = [ordered]@{
        meta     = $script:Meta
        steps    = @($script:Steps)
        commands = @($script:Commands)
        pytest   = $script:Pytest
    }
    $json = ConvertTo-Json -InputObject $obj -Depth 8
    Write-Text (Join-Path $OutDir 'results.json') $json
}

function Add-Step([string]$Id, [string]$Title, [string]$Status, [string]$Detail, $ExitCode = $null, [string]$Command = '') {
    $s = [ordered]@{ id = $Id; title = $Title; status = $Status; detail = $Detail }
    if ($null -ne $ExitCode) { $s['exit_code'] = [int]$ExitCode }
    if ($Command) { $s['command'] = $Command }
    [void]$script:Steps.Add($s)
    Save-Results
    $color = 'Gray'
    if ($Status -eq 'PASS') { $color = 'Green' } elseif ($Status -eq 'FAIL') { $color = 'Red' } elseif ($Status -eq 'BLOCKED') { $color = 'Yellow' }
    Write-Host ("[{0}] {1}: {2}" -f $Status, $Id, $Detail) -ForegroundColor $color
}

# A required step cannot continue: record it and stop the run (remaining steps become NOT RUN).
function Stop-Run([string]$Id, [string]$Title, [string]$Status, [string]$Detail, $ExitCode = $null, [string]$Command = '') {
    Add-Step $Id $Title $Status $Detail $ExitCode $Command
    throw 'VALIDATION_STOP'
}

function Format-Arg([string]$a) {
    if ($a -match '[\s"]') { return '"' + ($a -replace '"', '\"') + '"' }
    return $a
}

# Runs an executable, captures stdout/stderr into <LogName>.log, records the command and exit code.
function Invoke-Logged([string]$Exe, [string[]]$ArgList, [string]$LogName) {
    $out = Join-Path $OutDir ($LogName + '.stdout.txt')
    $err = Join-Path $OutDir ($LogName + '.stderr.txt')
    $display = (@($Exe) + $ArgList | ForEach-Object { Format-Arg $_ }) -join ' '
    Write-Host ("> " + $display) -ForegroundColor DarkGray
    $sp = @{
        FilePath               = $Exe
        WorkingDirectory       = $RepoRoot
        NoNewWindow            = $true
        Wait                   = $true
        PassThru               = $true
        RedirectStandardOutput = $out
        RedirectStandardError  = $err
    }
    if ($ArgList -and $ArgList.Count -gt 0) { $sp['ArgumentList'] = (($ArgList | ForEach-Object { Format-Arg $_ }) -join ' ') }
    $p = Start-Process @sp
    $code = $p.ExitCode
    $text = ''
    if (Test-Path -LiteralPath $out) { $text += [System.IO.File]::ReadAllText($out) }
    if (Test-Path -LiteralPath $err) { $text += [System.IO.File]::ReadAllText($err) }
    Write-Text (Join-Path $OutDir ($LogName + '.log')) $text
    [void]$script:Commands.Add([ordered]@{ command = $display; exit_code = $code; log = ($LogName + '.log') })
    Save-Results
    return [pscustomobject]@{ ExitCode = $code; Text = $text; Stdout = $(if (Test-Path -LiteralPath $out) { [System.IO.File]::ReadAllText($out) } else { '' }) }
}

function Get-Tail([string]$Text, [int]$Lines = 12) {
    $arr = $Text -split "`r?`n" | Where-Object { $_ -ne '' }
    if ($arr.Count -le $Lines) { return ($arr -join ' / ') }
    return (($arr | Select-Object -Last $Lines) -join ' / ')
}

$Titles = @{
    env_os = 'Windows 10/11 x64 detected'
    env_python = 'CPython 3.12 x64 detected'
    venv = 'Isolated virtual environment created'
    pip_install = 'Project requirements installed (requirements-dev.txt)'
    imports = 'Required packages importable'
    pytest = 'Complete pytest suite'
    compileall = 'compileall of all project Python sources'
    gui_import = 'PySide6 + ui.main_window import (no window shown)'
}

$ExitCodeOut = 1
try {
    Write-Host "AegisSec Enterprise - Windows validation  ($Stamp UTC)" -ForegroundColor Cyan
    Write-Host "Repository: $RepoRoot"
    Write-Host "Results:    $OutDir"
    $script:Meta['started_utc'] = (Get-Date).ToUniversalTime().ToString('o')
    $script:Meta['powershell'] = $PSVersionTable.PSVersion.ToString()
    # Platform facts are recorded explicitly and only upgraded after the OS checks below succeed.
    $script:Meta['is_windows'] = $false
    $script:Meta['mode'] = 'UNCONFIRMED (platform not yet checked)'

    # commit information (git may be absent when the project came from a ZIP)
    $script:Meta['commit'] = 'unknown (git not available)'
    if (Get-Command git -ErrorAction SilentlyContinue) {
        try {
            $c = (& git -C $RepoRoot rev-parse HEAD 2>$null)
            if ($LASTEXITCODE -eq 0 -and $c) { $script:Meta['commit'] = ($c | Select-Object -First 1) }
            $dirty = (& git -C $RepoRoot status --porcelain 2>$null)
            $script:Meta['worktree_dirty'] = [bool]$dirty
        } catch { }
    }

    # ---- 1. OS -------------------------------------------------------------------------
    $isWin = ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT)
    if (-not $isWin) {
        $script:Meta['is_windows'] = $false
        $script:Meta['mode'] = 'NOT WINDOWS'
        Stop-Run 'env_os' $Titles.env_os 'BLOCKED' ("This is not Windows (" + [System.Environment]::OSVersion.VersionString + "). Run this script on Windows 10/11 x64.")
    }
    $osInfo = Get-CimInstance -ClassName Win32_OperatingSystem
    $ver = [version]$osInfo.Version
    $arch = $env:PROCESSOR_ARCHITECTURE
    if ($env:PROCESSOR_ARCHITEW6432) { $arch = $env:PROCESSOR_ARCHITEW6432 }
    $script:Meta['os'] = $osInfo.Caption
    $script:Meta['os_build'] = $osInfo.Version + ' (build ' + $osInfo.BuildNumber + ')'
    $script:Meta['architecture'] = $arch
    $okOs = ($ver.Major -eq 10) -and ($osInfo.Caption -match 'Windows 1[01]') -and ($osInfo.ProductType -eq 1)
    if (-not $okOs) {
        Stop-Run 'env_os' $Titles.env_os 'BLOCKED' ("Not a Windows 10/11 client OS: " + $osInfo.Caption + " " + $osInfo.Version)
    }
    if ($arch -ne 'AMD64' -or -not [System.Environment]::Is64BitOperatingSystem) {
        Stop-Run 'env_os' $Titles.env_os 'BLOCKED' ("Processor architecture is '$arch'; x64 (AMD64) is required.")
    }
    # Windows 10/11 client, x64: confirmed. Only now may the run be reported as a Windows run.
    $script:Meta['is_windows'] = $true
    $script:Meta['mode'] = 'WINDOWS'
    Add-Step 'env_os' $Titles.env_os 'PASS' ($osInfo.Caption + ' ' + $osInfo.Version + ' ' + $arch)

    # ---- 2. Python ---------------------------------------------------------------------
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += , @('py', @('-3.12')) }
    if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += , @('python', @()) }
    $probeScript = Join-Path $PSScriptRoot 'windows_validation.py'
    $found = $null
    $seen = @()
    foreach ($cand in $candidates) {
        $exe = $cand[0]; $pre = @($cand[1])
        $r = Invoke-Logged $exe ($pre + @($probeScript, 'probe')) ('probe_' + $exe)
        if ($r.ExitCode -ne 0) { $seen += "$exe : exit $($r.ExitCode)"; continue }
        try { $info = $r.Stdout | ConvertFrom-Json } catch { $seen += "$exe : unreadable output"; continue }
        $v = @($info.version)
        $seen += ("$exe : Python " + ($v -join '.') + " " + $info.bits + "-bit " + $info.machine + " " + $info.implementation)
        if ($v[0] -eq 3 -and $v[1] -eq 12 -and $info.bits -eq 64 -and $info.machine -eq 'AMD64' -and $info.implementation -eq 'cpython') {
            $found = $info; break
        }
    }
    if (-not $found) {
        Stop-Run 'env_python' $Titles.env_python 'BLOCKED' ("No CPython 3.12 x64 interpreter found. Seen: " + ($seen -join '; ') + ". Install Python 3.12 (64-bit) from python.org and re-run.")
    }
    $script:SysPy = $found.executable
    $script:Meta['python'] = ("CPython " + (@($found.version) -join '.') + " " + $found.bits + "-bit " + $found.machine)
    $script:Meta['executable'] = $found.executable
    Add-Step 'env_python' $Titles.env_python 'PASS' ($script:Meta['python'] + ' at ' + $found.executable)

    # ---- 3. virtual environment ----------------------------------------------------------
    $venvDir = Join-Path $RepoRoot ('.venv-validate-' + $Stamp)
    $r = Invoke-Logged $script:SysPy @('-m', 'venv', $venvDir) 'venv'
    $script:VenvPy = Join-Path $venvDir 'Scripts\python.exe'
    if ($r.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $script:VenvPy)) {
        Stop-Run 'venv' $Titles.venv 'BLOCKED' ("venv creation failed: " + (Get-Tail $r.Text)) $r.ExitCode ("python -m venv " + $venvDir)
    }
    Add-Step 'venv' $Titles.venv 'PASS' ("created " + $venvDir) $r.ExitCode

    # ---- 4. install requirements ------------------------------------------------------------
    $pipArgs = @('-m', 'pip', 'install', '-r', (Join-Path $RepoRoot 'requirements-dev.txt'))
    if ($WheelDir) { $pipArgs += @('--no-index', '--find-links', (Resolve-Path -LiteralPath $WheelDir).Path) }
    $r = Invoke-Logged $script:VenvPy $pipArgs 'pip_install'
    if ($r.ExitCode -ne 0) {
        $missing = @()
        foreach ($m in [regex]::Matches($r.Text, 'No matching distribution found for ([^\s]+)')) { $missing += $m.Groups[1].Value }
        foreach ($m in [regex]::Matches($r.Text, 'Could not find a version that satisfies the requirement ([^\s]+)')) { $missing += $m.Groups[1].Value }
        $missing = $missing | Select-Object -Unique
        $what = if ($missing) { "Missing/uninstallable package(s): " + ($missing -join ', ') + ". " } else { "Package(s) not identified from the log. " }
        Stop-Run 'pip_install' $Titles.pip_install 'BLOCKED' ($what + "pip exit " + $r.ExitCode + ". Tail: " + (Get-Tail $r.Text)) $r.ExitCode 'pip install -r requirements-dev.txt'
    }
    $fr = Invoke-Logged $script:VenvPy @('-m', 'pip', 'list', '--format=freeze') 'pip_freeze'
    $script:Meta['packages'] = @($fr.Stdout -split "`r?`n" | Where-Object { $_ -ne '' })
    Add-Step 'pip_install' $Titles.pip_install 'PASS' ((@($script:Meta['packages']).Count).ToString() + " packages installed") $r.ExitCode 'pip install -r requirements-dev.txt'

    # ---- 5. imports -----------------------------------------------------------------------
    $r = Invoke-Logged $script:VenvPy @($probeScript, 'imports', 'PySide6', 'httpx', 'reportlab', 'pytest', 'pypdf', 'pdfplumber') 'imports'
    if ($r.ExitCode -ne 0) {
        $miss = @()
        try {
            $j = $r.Stdout | ConvertFrom-Json
            foreach ($n in @('PySide6', 'httpx', 'reportlab', 'pytest', 'pypdf', 'pdfplumber')) { if (-not $j.$n) { $miss += $n } }
        } catch { $miss += '(unreadable result)' }
        Stop-Run 'imports' $Titles.imports 'BLOCKED' ("Required package(s) not importable: " + ($miss -join ', ') + ". " + (Get-Tail $r.Text 4)) $r.ExitCode
    }
    Add-Step 'imports' $Titles.imports 'PASS' (($r.Stdout).Trim()) $r.ExitCode

    # ---- 6. pytest ------------------------------------------------------------------------
    $junit = Join-Path $OutDir 'pytest-junit.xml'
    $r = Invoke-Logged $script:VenvPy @('-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--junitxml', $junit) 'pytest'
    $ptDetail = ''
    $ptStatus = 'FAIL'
    if (Test-Path -LiteralPath $junit) {
        $s = Invoke-Logged $script:SysPy @($probeScript, 'junit', $junit) 'pytest_summary'
        try {
            $script:Pytest = $s.Stdout | ConvertFrom-Json
            $ptDetail = ("tests=" + $script:Pytest.tests + " passed=" + $script:Pytest.passed + " failed=" + $script:Pytest.failures + " errors=" + $script:Pytest.errors + " skipped=" + $script:Pytest.skipped)
            if ($r.ExitCode -eq 0 -and $script:Pytest.failures -eq 0 -and $script:Pytest.errors -eq 0 -and $script:Pytest.tests -gt 0) { $ptStatus = 'PASS' }
            if ($script:Pytest.skipped -gt 0) { $ptDetail += ' (skipped tests are listed in REPORT.md; a skip is not a pass)' }
        } catch { $ptDetail = 'JUnit file could not be summarised' }
    } else {
        $ptDetail = 'no JUnit file produced; ' + (Get-Tail $r.Text 6)
    }
    Add-Step 'pytest' $Titles.pytest $ptStatus $ptDetail $r.ExitCode 'python -m pytest -q'

    # ---- 7. compileall ----------------------------------------------------------------------
    $r = Invoke-Logged $script:VenvPy @('-m', 'compileall', '-q', '-f', 'app.py', 'core', 'reporting', 'ui', 'tools', 'tests') 'compileall'
    $st = if ($r.ExitCode -eq 0) { 'PASS' } else { 'FAIL' }
    Add-Step 'compileall' $Titles.compileall $st $(if ($r.ExitCode -eq 0) { 'all sources compile' } else { Get-Tail $r.Text 8 }) $r.ExitCode 'python -m compileall -q -f ...'

    # ---- 8. GUI import (no window) --------------------------------------------------------------
    $env:QT_QPA_PLATFORM = 'offscreen'
    $r = Invoke-Logged $script:VenvPy @($probeScript, 'guiimport') 'gui_import'
    Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    $st = if ($r.ExitCode -eq 0) { 'PASS' } else { 'FAIL' }
    Add-Step 'gui_import' $Titles.gui_import $st (($r.Stdout).Trim() + $(if ($r.ExitCode -ne 0) { ' ' + (Get-Tail $r.Text 6) } else { '' })) $r.ExitCode

    # ---- 9. PDF export checks (local Windows file system) ---------------------------------------------
    $chkArgs = @($probeScript, 'checks', '--out', $OutDir, '--rounds', "$Rounds", '--procs', "$Procs")
    if ($WorkDir) { $chkArgs += @('--work-dir', $WorkDir) }
    $r = Invoke-Logged $script:VenvPy $chkArgs 'pdf_checks'
    $checksJson = Join-Path $OutDir 'checks.json'
    if (Test-Path -LiteralPath $checksJson) {
        $cj = [System.IO.File]::ReadAllText($checksJson) | ConvertFrom-Json
        $script:Meta['fs'] = $cj.meta.fs
        $script:Meta['work_dir'] = $cj.meta.work_dir
        $script:Meta['reportlab'] = $cj.meta.reportlab
        foreach ($s in @($cj.steps)) { Add-Step $s.id $s.title $s.status $s.detail }
    } else {
        foreach ($id in @('pdf_demo', 'pdf_local_export', 'pdf_no_overwrite', 'pdf_concurrent', 'pdf_cleanup')) {
            Add-Step $id $id 'FAIL' ("checks.json was not produced (exit " + $r.ExitCode + "): " + (Get-Tail $r.Text 8))
        }
    }
}
catch {
    if ($_.Exception.Message -ne 'VALIDATION_STOP') {
        Add-Step 'script_error' 'Unexpected script error' 'FAIL' ($_.Exception.Message + ' @ ' + $_.InvocationInfo.PositionMessage)
    }
}
finally {
    $script:Meta['finished_utc'] = (Get-Date).ToUniversalTime().ToString('o')
    Save-Results
    $py = $script:SysPy
    if (-not $py -and (Get-Command py -ErrorAction SilentlyContinue)) { $py = 'py' }
    if (-not $py -and (Get-Command python -ErrorAction SilentlyContinue)) { $py = 'python' }
    $reportPath = Join-Path $OutDir 'REPORT.md'
    if ($py -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'windows_validation.py'))) {
        $a = @((Join-Path $PSScriptRoot 'windows_validation.py'), 'report', (Join-Path $OutDir 'results.json'), '--out', $reportPath)
        if ($py -eq 'py') { $a = @('-3') + $a }
        & $py @a | Out-Null
    } else {
        Write-Host "No Python available to render REPORT.md; see results.json." -ForegroundColor Yellow
    }

    $bad = @($script:Steps | Where-Object { $_.status -ne 'PASS' })
    $notReached = (@($Titles.Keys) + @('pdf_demo', 'pdf_local_export', 'pdf_no_overwrite', 'pdf_concurrent', 'pdf_cleanup')) |
        Where-Object { $id = $_; -not ($script:Steps | Where-Object { $_.id -eq $id }) }
    if ($script:Steps.Count -gt 0 -and $bad.Count -eq 0 -and @($notReached).Count -eq 0) { $ExitCodeOut = 0 } else { $ExitCodeOut = 1 }

    Write-Host ''
    Write-Host '==================== SUMMARY ====================' -ForegroundColor Cyan
    foreach ($k in @('PASS', 'FAIL', 'BLOCKED')) {
        Write-Host ("{0,-8} {1}" -f $k, @($script:Steps | Where-Object { $_.status -eq $k }).Count)
    }
    Write-Host ("NOT RUN  " + @($notReached).Count + "  (steps never reached)")
    if ($ExitCodeOut -eq 0) {
        Write-Host 'Automated checks: ALL PASS. GUI smoke test is still NOT RUN (manual). Persian PDF and dependency audit are NOT validated.' -ForegroundColor Green
    } else {
        Write-Host 'Automated checks: NOT ALL PASS. See REPORT.md.' -ForegroundColor Red
    }
    Write-Host "Report:  $reportPath"
    Write-Host "Results: $(Join-Path $OutDir 'results.json')"
}
exit $ExitCodeOut
