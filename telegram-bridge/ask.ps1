<#
.SYNOPSIS
    ask.ps1 - Windows PowerShell twin of ask.sh. Send the founder a question
    card with one button per option.

.DESCRIPTION
    Same contract as ask.sh:
        .\ask.ps1 "Which database?" "Postgres (recommended)" "SQLite" "Park this"
        .\ask.ps1 --reply-to 1234 "Ship it?" "Yes" "Not yet"
        .\ask.ps1 --clear <card_message_id>    # remove a card's buttons

    Prints the card's message_id on success. Thin wrapper around ask.py so
    the Unix (ask.sh) and Windows entry points share one implementation -
    see ask.py's header for what bot.py does when a button is tapped.

    Python is resolved the way install-windows-task.ps1 does it:
    venv\Scripts\python.exe next to this script if present, else `python`
    via Get-Command.

    Written for Windows PowerShell 5.1 and PowerShell 7+ (pwsh); not yet
    exercised under either or on a real Windows host.

.EXIT CODES
    ask.py's own exit code, unchanged. 1 if no Python interpreter is found.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($ScriptDir)) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$python = $null
$venvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $python = $venvPython
} else {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source }
}
if ([string]::IsNullOrEmpty($python)) {
    [Console]::Error.WriteLine("Error: could not find a Python interpreter (no venv\Scripts\python.exe next to this script, no python on PATH).")
    exit 1
}

# ask.py writes its own stdout/stderr straight through; only its exit code
# needs carrying over.
& $python (Join-Path $ScriptDir "ask.py") @args
exit $LASTEXITCODE
