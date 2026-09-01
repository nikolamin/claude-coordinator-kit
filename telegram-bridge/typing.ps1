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

    Compatible with Windows PowerShell 5.1 and PowerShell 7+ (pwsh).

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
            Write-BridgeError "curl request to Telegram API failed, or Telegram API returned an error response."
        }
    } catch {
        Write-BridgeError "curl request to Telegram API failed, or Telegram API returned an error response."
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
    Start-Process -FilePath $hostExe -ArgumentList @('-NoProfile', '-NonInteractive', '-Command', $childCommand) `
        -WindowStyle Hidden | Out-Null
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
