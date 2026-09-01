<#
.SYNOPSIS
    react.ps1 - Windows PowerShell port of react.sh. Set a reaction on a
    relayed Telegram message.

.DESCRIPTION
    Same contract as react.sh:
        .\react.ps1 [--chat <chat_id>] <message_id> <result>

    <result> maps a friendly word to one of Telegram's curated allowed-emoji
    reactions (identical vocabulary/meaning to react.sh):
        ok, done, check, thumbup   -> (thumbs up)  finished, all good
        fail, down, thumbdown, x   -> (thumbs down) failed / went wrong
        seen, working              -> (eyes) picked up, still working
        thinking                   -> (thinking face) actively reasoning
        an ASCII word (letters only) not in the list above -> rejected
            locally, exit 1, before any network call.
        anything else (an actual emoji, or other non-word input) -> used
            AS-IS as a literal emoji.

    By default the reaction is set in TELEGRAM_CHAT_ID (the founder's
    private DM) - pass --chat <chat_id> to react on a message in a
    different chat instead (e.g. a group chat_id from relay-inbox.jsonl's
    "chat_id" field for a group-relayed message).

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from a .env file located
    next to this script (NOT the caller's working directory) - same
    resolution as notify.ps1.

    Compatible with Windows PowerShell 5.1 and PowerShell 7+ (pwsh).

.EXIT CODES
    0 on success. 1 on any failure (bad usage, unrecognized reaction word,
    missing .env, missing token/chat id, a real Telegram API error) -
    matches react.sh exactly.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($ScriptDir)) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

. (Join-Path $ScriptDir "telegram_common.ps1")

function Get-ReactionEmoji {
    <#
    .SYNOPSIS
        Map a react.ps1 <result> word to its Telegram-allowed emoji, per
        the vocabulary documented in react.sh / SETUP.md (j). Case-sensitive,
        matching the bash `case` statement react.sh uses (all keywords are
        lowercase). Returns:
          - the emoji string, for a recognized word or a pass-through
            literal (anything that ISN'T an ASCII-letters-only word);
          - $null, to signal "unrecognized ASCII word - caller must error
            out locally before any network call" (mirrors react.sh's
            `if [[ "$RESULT" =~ ^[A-Za-z]+$ ]]` branch).
    #>
    param([Parameter(Mandatory = $true)][string]$Result)

    if ($Result -cmatch '^(ok|done|check|thumbup)$') { return [char]::ConvertFromUtf32(0x1F44D) }   # (thumbs up)
    if ($Result -cmatch '^(fail|down|thumbdown|x)$') { return [char]::ConvertFromUtf32(0x1F44E) }    # (thumbs down)
    if ($Result -cmatch '^(seen|working)$') { return [char]::ConvertFromUtf32(0x1F440) }             # (eyes)
    if ($Result -cmatch '^(thinking)$') { return [char]::ConvertFromUtf32(0x1F914) }                 # (thinking face)

    if ($Result -cmatch '^[A-Za-z]+$') {
        return $null
    }
    return $Result
}

# --- argument parsing -------------------------------------------------------
$argv = $args
$chatOverride = $null
$haveChatOverride = $false

if ($argv.Count -gt 0 -and $argv[0] -eq "--chat") {
    if ($argv.Count -lt 2 -or [string]::IsNullOrEmpty($argv[1])) {
        Write-BridgeError "--chat requires a chat_id argument"
    }
    $chatOverride = $argv[1]
    $haveChatOverride = $true
    if ($argv.Count -gt 2) {
        $argv = $argv[2..($argv.Count - 1)]
    } else {
        $argv = @()
    }
}

$messageId = $null
$resultWord = $null
if ($argv.Count -ge 1) { $messageId = $argv[0] }
if ($argv.Count -ge 2) { $resultWord = $argv[1] }

if ([string]::IsNullOrEmpty($messageId) -or [string]::IsNullOrEmpty($resultWord)) {
    Write-BridgeError "usage: react.ps1 [--chat <chat_id>] <message_id> <result>`n  <result>: ok|done|check|thumbup, fail|down|thumbdown|x, seen|working (eyes), thinking, or any other literal emoji."
}

if ($messageId -notmatch '^[0-9]+$') {
    Write-BridgeError "<message_id> must be a positive integer, got: $messageId"
}

$emoji = Get-ReactionEmoji -Result $resultWord
if ($null -eq $emoji) {
    Write-BridgeError "unrecognized reaction word: $resultWord`n  known words: ok|done|check|thumbup, fail|down|thumbdown|x, seen|working, thinking. Pass a literal emoji instead if that's what you meant."
}

# --- config ------------------------------------------------------------------
# Inlined to match react.sh's exact check order/messages (NOT
# Assert-BridgeConfigured, which always requires both vars unconditionally -
# see that function's own docstring in telegram_common.ps1 for why react.ps1
# is one of its two documented exceptions): react.sh checks
# TELEGRAM_BOT_TOKEN first (independent of --chat), then only requires
# TELEGRAM_CHAT_ID when no --chat override was given.
$envFile = Join-Path $ScriptDir ".env"
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    Write-BridgeError ".env not found at $envFile`n  Copy .env.example to .env and fill in TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID."
}
$envVars = Read-DotEnv -Path $envFile
$token = $envVars['TELEGRAM_BOT_TOKEN']
$apiBase = Get-TelegramApiBase -EnvVars $envVars

if ([string]::IsNullOrEmpty($token)) {
    Write-BridgeError "TELEGRAM_BOT_TOKEN not set in $envFile"
}

$targetChatId = $null
if ($haveChatOverride) {
    $targetChatId = $chatOverride
} elseif (-not [string]::IsNullOrEmpty($envVars['TELEGRAM_CHAT_ID'])) {
    $targetChatId = $envVars['TELEGRAM_CHAT_ID']
} else {
    Write-BridgeError "TELEGRAM_CHAT_ID not set in $envFile (or pass --chat <chat_id>)"
}

# --- send ----------------------------------------------------------------
# Telegram's setMessageReaction takes `reaction` as a JSON array of
# reaction objects, url-encoded the same way notify.sh/react.sh pass it -
# Invoke-RestMethod's -Body hashtable already form-urlencodes every value,
# including this JSON string, so no manual encoding is needed here.
$reactionArray = @(@{ type = "emoji"; emoji = $emoji })
$reactionJson = ($reactionArray | ConvertTo-Json -Compress)
# ConvertTo-Json on a single-element array can collapse to a scalar object
# instead of a JSON array in some PowerShell versions - force array syntax
# explicitly so Telegram always receives a JSON array, never a bare object.
if (-not $reactionJson.TrimStart().StartsWith('[')) {
    $reactionJson = "[$reactionJson]"
}

Invoke-TelegramForm -ApiBase $apiBase -Token $token -Method "setMessageReaction" -Body @{
    chat_id    = $targetChatId
    message_id = $messageId
    reaction   = $reactionJson
} | Out-Null

exit 0
