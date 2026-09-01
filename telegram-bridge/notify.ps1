<#
.SYNOPSIS
    notify.ps1 - Windows PowerShell port of notify.sh. Ping your phone via
    Telegram from any PowerShell session, scheduled task, or hook.

.DESCRIPTION
    Same contract as notify.sh:
        .\notify.ps1 "some message"            # send to the founder's DM (default)
        .\notify.ps1 --group "some message"    # send to the auto-discovered group chat

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from a .env file located
    next to this script (NOT the caller's working directory), so it is safe
    to call from any other PowerShell session, project, or scheduled task
    regardless of where that caller's working directory is.

    --group reads the group chat id from bridge-config.json's
    "active_group_chat_id" (next to this script), auto-populated by bot.py
    the first time it observes a message in a group it's a member of - no
    manual setup step. See SETUP.md "Group chat support" / "Windows (Task
    Scheduler)".

    PowerShell quoting note (see SETUP.md): a backtick is PowerShell's
    escape character and "$name" expands inside double-quoted strings -
    the message argument must never contain a backtick or an unintended
    "$", same class of hazard notify.sh already warns about for bash
    backtick command substitution.

    Written for Windows PowerShell 5.1 and PowerShell 7+ (pwsh); exercised under
    PowerShell 7 against a stub API, not yet under 5.1 or on a real Windows host.

.EXIT CODES
    0 on success. 1 on any failure (missing .env, missing token/chat id,
    bad usage, a real Telegram API error) - matches notify.sh exactly.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($ScriptDir)) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

. (Join-Path $ScriptDir "telegram_common.ps1")

# --- argument parsing -------------------------------------------------------
$argv = $args
$target = "dm"
if ($argv.Count -gt 0 -and $argv[0] -eq "--group") {
    $target = "group"
    if ($argv.Count -gt 1) {
        $argv = $argv[1..($argv.Count - 1)]
    } else {
        $argv = @()
    }
}

if ($argv.Count -lt 1 -or [string]::IsNullOrEmpty($argv[0])) {
    Write-BridgeError "usage: notify.ps1 [--group] `"<message>`"`n  A non-empty message is required as the first argument."
}
$message = $argv[0]

# --- config ------------------------------------------------------------------
$envVars = Assert-BridgeConfigured -ScriptDir $ScriptDir
$token = $envVars['TELEGRAM_BOT_TOKEN']
$apiBase = Get-TelegramApiBase -EnvVars $envVars

$targetChatId = $envVars['TELEGRAM_CHAT_ID']

if ($target -eq "group") {
    $bridgeConfigFile = Join-Path $ScriptDir "bridge-config.json"
    if (-not (Test-Path -LiteralPath $bridgeConfigFile -PathType Leaf)) {
        Write-BridgeError "no group chat known yet ($bridgeConfigFile not found).`n  Add the bot to the group and send any message that mentions it first - bot.py auto-discovers the group chat id."
    }
    try {
        $raw = Get-Content -LiteralPath $bridgeConfigFile -Raw -Encoding UTF8
        $cfg = $raw | ConvertFrom-Json
    } catch {
        Write-BridgeError "bridge-config.json at $bridgeConfigFile could not be parsed."
    }
    $activeGroupChatId = $null
    if ($cfg.PSObject.Properties.Name -contains 'active_group_chat_id') {
        $activeGroupChatId = $cfg.active_group_chat_id
    }
    if ($null -eq $activeGroupChatId -or [string]::IsNullOrEmpty([string]$activeGroupChatId)) {
        Write-BridgeError "bridge-config.json has no active_group_chat_id yet - group not discovered."
    }
    $targetChatId = $activeGroupChatId
}

# --- send ----------------------------------------------------------------
Invoke-TelegramForm -ApiBase $apiBase -Token $token -Method "sendMessage" -Body @{
    chat_id = $targetChatId
    text    = $message
} | Out-Null

exit 0
