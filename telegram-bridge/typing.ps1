<#
.SYNOPSIS
    typing.ps1 - Windows PowerShell port of typing.sh. Post (or keep alive)
    Telegram's "typing..." chat action.

.DESCRIPTION
    Same contract as typing.sh:
        .\typing.ps1              # one-shot ping, Telegram auto-expires it after ~5s
        .\typing.ps1 <seconds>    # keep-alive: re-sends every ~4s for <seconds>
                                   # seconds, then stops on its own. Runs as a
                                   # DETACHED background process (a fresh
                                   # PowerShell host, same engine as this
                                   # script - powershell.exe or pwsh.exe,
                                   # whichever launched this script), so this
                                   # script itself returns immediately no
                                   # matter how the caller invokes it -
                                   # nothing to clean up, no job/process for
                                   # the caller to track.

    The bot token/chat id/API base are handed to the detached child process
    via environment variables (never via its command line), so a token
    never appears in `Get-Process`/Task Manager command-line inspection the
    way it would if interpolated into an -ArgumentList string - matches
    this repo's "never print/expose the token" discipline (see
    telegram_common.ps1's module docstring).

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from a .env file located
    next to this script (NOT the caller's working directory) - same
    resolution as notify.ps1.

    Written for Windows PowerShell 5.1 and PowerShell 7+ (pwsh); exercised under
    PowerShell 7 against a stub API, not yet under 5.1 or on a real Windows host.

.EXIT CODES
    0 on success (including "keep-alive process started" - its own
    individual pings are best-effort and never reported back to the
    caller, same as typing.sh). 1 on any failure (bad usage, missing .env,
    missing token/chat id, or - for the one-shot form only - a real
    Telegram API error).
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($ScriptDir)) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

. (Join-Path $ScriptDir "telegram_common.ps1")

# --- argument parsing -------------------------------------------------------
$durationArg = "0"
if ($args.Count -gt 0) { $durationArg = [string]$args[0] }

if ($durationArg -notmatch '^[0-9]+$') {
    Write-BridgeError "usage: typing.ps1 [seconds]`n  <seconds>, if given, must be a non-negative integer."
}
$duration = [int]$durationArg

# --- config ------------------------------------------------------------------
$envVars = Assert-BridgeConfigured -ScriptDir $ScriptDir
$token = $envVars['TELEGRAM_BOT_TOKEN']
$chatId = $envVars['TELEGRAM_CHAT_ID']
$apiBase = Get-TelegramApiBase -EnvVars $envVars

# --- one-shot path -----------------------------------------------------------
if ($duration -le 0) {
    try {
        $response = Invoke-RestMethod -Uri "$apiBase/bot$token/sendChatAction" -Method Post `
            -Body @{ chat_id = $chatId; action = "typing" } -UseBasicParsing -TimeoutSec 10
        if (-not $response.ok) {
            Write-BridgeError "request to Telegram API failed, or Telegram API returned an error response."
        }
    } catch {
        Write-BridgeError "request to Telegram API failed, or Telegram API returned an error response."
    }
    exit 0
}

# --- keep-alive path: detached background process --------------------------
# TYPING_INTERVAL_SECONDS in bot.py uses the same ~4s interval, since
# Telegram's typing indicator lasts ~5s client-side - see typing.sh's own
# header comment for the full rationale.
$hostExe = $null
try {
    $hostExe = (Get-Process -Id $PID).Path
} catch { }
if ([string]::IsNullOrEmpty($hostExe)) {
    # Fall back to whatever engine is currently running this script.
    if ($PSVersionTable.PSEdition -eq 'Core') { $hostExe = "pwsh" } else { $hostExe = "powershell" }
}

# Environment-variable handoff (see .DESCRIPTION above): the child process
# inherits the current process's environment block by default when
# launched via Start-Process, so these never appear on the child's command
# line / in any process listing.
$env:TELEGRAM_BRIDGE_TYPING_TOKEN = $token
$env:TELEGRAM_BRIDGE_TYPING_CHATID = $chatId
$env:TELEGRAM_BRIDGE_TYPING_APIBASE = $apiBase
$env:TELEGRAM_BRIDGE_TYPING_DURATION = [string]$duration

$childCommand = @'
Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"
$token = $env:TELEGRAM_BRIDGE_TYPING_TOKEN
$chatId = $env:TELEGRAM_BRIDGE_TYPING_CHATID
$apiBase = $env:TELEGRAM_BRIDGE_TYPING_APIBASE
$duration = [int]$env:TELEGRAM_BRIDGE_TYPING_DURATION
Remove-Item Env:TELEGRAM_BRIDGE_TYPING_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:TELEGRAM_BRIDGE_TYPING_CHATID -ErrorAction SilentlyContinue
Remove-Item Env:TELEGRAM_BRIDGE_TYPING_APIBASE -ErrorAction SilentlyContinue
Remove-Item Env:TELEGRAM_BRIDGE_TYPING_DURATION -ErrorAction SilentlyContinue
function Send-TypingOnceChild {
    try {
        Invoke-RestMethod -Uri "$apiBase/bot$token/sendChatAction" -Method Post `
            -Body @{ chat_id = $chatId; action = "typing" } -UseBasicParsing -TimeoutSec 10 | Out-Null
    } catch {
        # Best-effort, same as typing.sh's keep-alive loop: a single failed
        # ping never aborts the rest of the loop, and nothing is printed
        # (this process has no console attached to print to anyway).
    }
}
$endTime = (Get-Date).AddSeconds($duration)
Send-TypingOnceChild
while ((Get-Date) -lt $endTime) {
    Start-Sleep -Seconds 4
    Send-TypingOnceChild
}
'@

try {
    # -ArgumentList joins its elements into a single unquoted command-line
    # string, and the child process's own argv parser strips the double
    # quotes back out of $childCommand before PowerShell ever sees them -
    # so `action = "typing"` arrives as `action = typing`, an unquoted bare
    # word that throws CommandNotFoundException deep inside the child
    # (silently swallowed by its own try/catch), producing zero pings but
    # still exit 0. -EncodedCommand sidesteps quoting entirely: the child
    # script travels as base64 of its UTF-16LE bytes and PowerShell decodes
    # it directly, with no command-line requoting step to mangle it.
    $encodedCommand = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($childCommand))

    # Redirect the detached child's stdout/stderr to the platform's null
    # device. Without this the child inherits THIS process's stdout/stderr,
    # so `typing.ps1 30 | cat` (or `$x = typing.ps1 30`) blocks the caller
    # for the full <seconds> duration instead of returning immediately -
    # measured 8.78s for a 6s run under a pipe, vs. 0.29s once redirected.
    # typing.sh's own detached subshell redirects the same way
    # (`>/dev/null 2>&1`) and its own comment calls that load-bearing.
    #
    # Start-Process refuses -RedirectStandardOutput and
    # -RedirectStandardError when they're the textually-identical path
    # ("... cannot be run because ... are same. Give different inputs...") -
    # confirmed under pwsh 7.4.6/macOS: "/dev/null" for both throws that
    # error. Each stream therefore needs its own distinct spelling of the
    # null device: on Unix, "/dev/null" and "/dev/zero" are two different
    # device files that both silently discard anything written to them
    # (verified here); on Windows, "NUL" and the UNC-style device path
    # "\\.\NUL" both resolve to the same null device, but as distinct
    # strings - unverified on a real Windows host, same as the rest of
    # this script per its own docstring above.
    $onWindowsHost = ($env:OS -eq 'Windows_NT')
    $nullOut = if ($onWindowsHost) { 'NUL' } else { '/dev/null' }
    $nullErr = if ($onWindowsHost) { '\\.\NUL' } else { '/dev/zero' }
    # -NoNewWindow (rather than -WindowStyle Hidden) suppresses the
    # detached child's console window here: on Windows PowerShell 5.1,
    # -WindowStyle sits in a different parameter set from
    # -RedirectStandardOutput/-RedirectStandardError, so combining them
    # fails to bind; -NoNewWindow shares the redirect parameter set on
    # both PS 5.1 and PowerShell 7 (pwsh), and is supported on pwsh under
    # macOS/Linux too (used here for cross-platform testing against the
    # stub API). A hidden window would buy nothing anyway, since the
    # child's output already goes to the null device above.
    $startArgs = @{
        FilePath               = $hostExe
        ArgumentList           = @('-NoProfile', '-NonInteractive', '-EncodedCommand', $encodedCommand)
        RedirectStandardOutput = $nullOut
        RedirectStandardError  = $nullErr
        NoNewWindow            = $true
    }
    Start-Process @startArgs | Out-Null
} finally {
    # Clear the handoff variables from THIS process's environment now that
    # Start-Process has copied them into the child's own environment block
    # - nothing sensitive lingers in this (about-to-exit) process either.
    Remove-Item Env:TELEGRAM_BRIDGE_TYPING_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:TELEGRAM_BRIDGE_TYPING_CHATID -ErrorAction SilentlyContinue
    Remove-Item Env:TELEGRAM_BRIDGE_TYPING_APIBASE -ErrorAction SilentlyContinue
    Remove-Item Env:TELEGRAM_BRIDGE_TYPING_DURATION -ErrorAction SilentlyContinue
}

exit 0
