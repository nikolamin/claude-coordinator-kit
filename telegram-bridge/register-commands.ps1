<#
.SYNOPSIS
    register-commands.ps1 - Windows PowerShell port of register-commands.sh.
    Register this bot's slash-command menu with Telegram.

.DESCRIPTION
    Same contract as register-commands.sh:
        .\register-commands.ps1            # merge the commands below into the bot's menu
        .\register-commands.ps1 --list     # print the currently registered menu, change nothing

    THE KIT SHIPS AN EMPTY MENU. $Commands below is deliberately empty:
    which commands make sense is a per-project question, so each project
    fills in its own (see the sample line). With the array empty this
    script is a safe no-op that only reports the currently registered menu
    - identical behavior to register-commands.sh's shipped default.

    IDEMPOTENT AND ADDITIVE: reads the existing menu via getMyCommands
    first and merges, so re-running never drops a command some other setup
    step registered, and running it twice is a no-op. A command listed
    below whose description changed is updated in place.

    Reads TELEGRAM_BOT_TOKEN from a .env file located next to this script
    (NOT the caller's working directory), same convention as the other
    .ps1 scripts in this directory.

    The token is never printed - see telegram_common.ps1's module
    docstring for the shared credential-handling discipline every script
    in this directory follows.

    Written for Windows PowerShell 5.1 and PowerShell 7+ (pwsh); exercised under
    PowerShell 7 against a stub API, not yet under 5.1 or on a real Windows host.

.EXIT CODES
    0 on success (including the "nothing to register" no-op path). 1 on
    any failure (missing .env, missing token, a real Telegram API error) -
    matches register-commands.sh exactly.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($ScriptDir)) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

. (Join-Path $ScriptDir "telegram_common.ps1")

# ---------------------------------------------------------------------------
# The commands this bridge registers. One "name|description" string per
# array entry - same "name|description" convention as register-commands.sh's
# COMMANDS bash array, so a project that has already filled in the .sh
# version can copy the same lines here verbatim.
# Telegram rules: name is lowercase a-z, 0-9 and underscores, 1-32 chars;
# description is 1-256 chars.
#
# Empty by default - this is the per-project slot. Uncomment the sample
# below (or write your own) to publish a menu.
#
# Sample (matching register-commands.sh's own sample):
#   "personas|Run a persona beta-test round on this project"
# ---------------------------------------------------------------------------
$Commands = @(
    # "yourcommand|What your project's coordinator does when it sees this"
)

$listOnly = $false
if ($args.Count -gt 0 -and $args[0] -eq "--list") {
    $listOnly = $true
}

# Inlined (NOT Assert-BridgeConfigured, which always requires
# TELEGRAM_CHAT_ID too - see that function's docstring in
# telegram_common.ps1): register-commands.sh only ever requires
# TELEGRAM_BOT_TOKEN, never TELEGRAM_CHAT_ID.
$envFile = Join-Path $ScriptDir ".env"
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    Write-BridgeError ".env not found at $envFile`n  Copy .env.example to .env and fill in TELEGRAM_BOT_TOKEN."
}
$envVars = Read-DotEnv -Path $envFile
$token = $envVars['TELEGRAM_BOT_TOKEN']
if ([string]::IsNullOrEmpty($token)) {
    Write-BridgeError "TELEGRAM_BOT_TOKEN not set in $envFile"
}
$apiBase = Get-TelegramApiBase -EnvVars $envVars

function Get-MyCommandsRaw {
    param([string]$ApiBase, [string]$Token)
    $uri = "$ApiBase/bot$Token/getMyCommands"
    # Invoke-WebRequest (not Invoke-RestMethod), same reasoning as
    # telegram_common.ps1's Invoke-TelegramForm: keeps the raw response
    # body text available for the error message below, matching
    # register-commands.sh's `grep -q '"ok":true' <<< "$EXISTING"` / `...
    # $EXISTING` wording even when the body isn't JSON at all.
    try {
        $webResponse = Invoke-WebRequest -Uri $uri -Method Get -UseBasicParsing -TimeoutSec 30
    } catch {
        # Match register-commands.sh's "Error: getMyCommands request to the
        # Telegram API failed." wording exactly - no HTTP-detail suffix.
        Write-BridgeError "getMyCommands request to the Telegram API failed."
    }
    $bodyText = $webResponse.Content
    # A 200 with a non-JSON body (e.g. a proxy's HTML error page) leaves
    # $response $null - under StrictMode, $response.ok on $null would throw
    # an unhandled PropertyNotFoundException instead of taking the intended
    # error path.
    $response = $null
    try { $response = $bodyText | ConvertFrom-Json } catch { }
    $hasOk = $false
    try { $hasOk = ($response -and ($response.PSObject.Properties.Name -contains 'ok')) } catch { }
    if (-not $hasOk) {
        Write-BridgeError "getMyCommands returned an error response: $bodyText"
    }
    if (-not $response.ok) {
        Write-BridgeError "getMyCommands returned an error response: $($response | ConvertTo-Json -Compress)"
    }
    return $response
}

$existing = Get-MyCommandsRaw -ApiBase $apiBase -Token $token

if ($listOnly) {
    Write-Output ($existing | ConvertTo-Json -Compress -Depth 10)
    exit 0
}

# An empty $Commands array is the shipped default, and it is a legitimate
# state, not an error - this bridge simply has no commands of its own to
# publish yet. Mirrors register-commands.sh's own early-exit for an empty
# COMMANDS array.
if ($Commands.Count -eq 0) {
    Write-Output "No commands defined in this script's `$Commands array; nothing to register."
    Write-Output "  Add a `"name|description`" line to `$Commands in $($MyInvocation.MyCommand.Path) to publish one."
    Write-Output "Currently registered menu:"
    Write-Output ($existing | ConvertTo-Json -Compress -Depth 10)
    exit 0
}

# Merge: start from whatever is already registered, then add/update ours.
# Order is preserved (existing commands first, in their existing order), so
# a re-run never reshuffles the founder's menu - same merge semantics as
# register-commands.sh's Python one-liner.
$existingList = @()
if ($existing.PSObject.Properties.Name -contains 'result' -and $existing.result) {
    $existingList = @($existing.result)
}

$merged = [System.Collections.Generic.List[hashtable]]::new()
$byName = @{}
foreach ($cmd in $existingList) {
    $entry = @{ command = $cmd.command; description = $cmd.description }
    $merged.Add($entry) | Out-Null
    $byName[$cmd.command] = $entry
}

foreach ($spec in $Commands) {
    $parts = $spec.Split('|', 2)
    if ($parts.Count -lt 2) { continue }
    $name = $parts[0]
    $desc = $parts[1]
    if ($byName.ContainsKey($name)) {
        $byName[$name]['description'] = $desc
    } else {
        $newEntry = @{ command = $name; description = $desc }
        $merged.Add($newEntry) | Out-Null
        $byName[$name] = $newEntry
    }
}

# Structural comparison against the untouched existing list: build both
# sides as JSON with a fixed key order so an unrelated JSON-property-order
# difference never causes a spurious "changed" result.
function ConvertTo-ComparableJson {
    param([System.Collections.IEnumerable]$Items)
    $ordered = @()
    foreach ($item in $Items) {
        $ordered += [PSCustomObject]@{ command = $item.command; description = $item.description }
    }
    return ($ordered | ConvertTo-Json -Compress -Depth 10)
}

$mergedJson = ConvertTo-ComparableJson -Items $merged
$existingJson = ConvertTo-ComparableJson -Items $existingList

if ($mergedJson -eq $existingJson) {
    Write-Output "Command menu already up to date; nothing to do."
    Write-Output ($existing | ConvertTo-Json -Compress -Depth 10)
    exit 0
}

$mergedArrayJson = ($merged | ForEach-Object { [PSCustomObject]@{ command = $_.command; description = $_.description } } | ConvertTo-Json -Compress -Depth 10)
# ConvertTo-Json collapses a single-element array to a bare object -
# Telegram's setMyCommands requires a JSON array even for one command.
if (-not $mergedArrayJson.TrimStart().StartsWith('[')) {
    $mergedArrayJson = "[$mergedArrayJson]"
}

$setUri = "$apiBase/bot$token/setMyCommands"
try {
    $setWebResponse = Invoke-WebRequest -Uri $setUri -Method Post -Body @{ commands = $mergedArrayJson } -UseBasicParsing -TimeoutSec 30
} catch {
    # Match register-commands.sh's "Error: setMyCommands request to the
    # Telegram API failed." wording exactly - no HTTP-detail suffix.
    Write-BridgeError "setMyCommands request to the Telegram API failed."
}
$setBodyText = $setWebResponse.Content
$setResponse = $null
try { $setResponse = $setBodyText | ConvertFrom-Json } catch { }
$setHasOk = $false
try { $setHasOk = ($setResponse -and ($setResponse.PSObject.Properties.Name -contains 'ok')) } catch { }
if (-not $setHasOk) {
    Write-BridgeError "Telegram API returned an error response: $setBodyText"
}
if (-not $setResponse.ok) {
    Write-BridgeError "Telegram API returned an error response: $($setResponse | ConvertTo-Json -Compress)"
}

# Read the menu back so the caller sees what is actually registered now
# (this response carries no secrets - safe to print).
$verify = Get-MyCommandsRaw -ApiBase $apiBase -Token $token
Write-Output "Command menu registered. getMyCommands now returns:"
Write-Output ($verify | ConvertTo-Json -Compress -Depth 10)

exit 0
