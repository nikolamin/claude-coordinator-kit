<#
.SYNOPSIS
    telegram_common.ps1 - Shared helpers for this directory's Windows
    PowerShell (.ps1) ports of notify.sh / react.sh / typing.sh /
    send-file.sh / register-commands.ps1's env+HTTP boilerplate.

.DESCRIPTION
    Dot-sourced by every other .ps1 script in this directory:
        . (Join-Path $PSScriptRoot "telegram_common.ps1")

    Mirrors telegram_common.py's role for bot.py/daily_report.py - a small
    shared module factoring out the .env parsing, redaction, and Telegram
    HTTP-call plumbing every .ps1 script here needs, so each individual
    script stays focused on its own contract (same "one script per job"
    shape as the .sh scripts, which duplicate this boilerplate inline
    rather than sharing a module - the .ps1 scripts share it instead purely
    as an internal implementation detail; the external contract documented
    in SETUP.md - `notify.ps1 "<text>"`, `react.ps1 <message_id> ok|fail`,
    etc. - is unaffected either way).

    Written for BOTH Windows PowerShell 5.1 and PowerShell 7+ (pwsh) on
    Windows: no `??`, no ternary `? :`, no `-Parallel`, no `?.`, no
    PS7-only cmdlet parameters. Exercised under PowerShell 7 against a
    stub API, not yet under 5.1 or on a real Windows host. See SETUP.md
    "Windows (Task Scheduler)" for the execution-policy note needed to
    actually run any of these scripts.

    CREDENTIAL HANDLING: every function in this file that can encounter the
    bot token (in a URL, in a caught exception) treats it the same way this
    repo's .sh scripts and Python files already do - it is read from `.env`
    and used only to build the outgoing request; it is never written to
    stdout, Write-Host, Write-Output, a log file, or an error message. On
    failure, only the HTTP status code and Telegram's own `description`
    field (a non-secret piece of the response body) are surfaced. As
    defense in depth, Get-RedactedText additionally scrubs any
    token-shaped substring out of arbitrary text before it is ever printed,
    the same regex telegram_common.py's redact_secrets() uses.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 runs on .NET Framework, whose HTTP stack
# (WebRequest/HttpWebRequest, and the ServicePointManager-backed
# HttpClient default handler that send-file.ps1's HttpClient also relies
# on) can default to an old SecurityProtocol that TLS-1.2-only endpoints
# like api.telegram.org reject outright - explicitly opt in here, once,
# before any request in this directory is made. No-op on PowerShell 7
# (.NET Core), where TLS 1.2 is already the OS-negotiated default and
# ServicePointManager.SecurityProtocol is a vestigial/no-op property; the
# try/catch is defense in depth for either case.
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch { }

$Script:TelegramDefaultApiBase = "https://api.telegram.org"

# Matches the bot-token segment of a Telegram Bot API URL, e.g.
# "https://api.telegram.org/bot123456:AAExampleTokenExample/getUpdates" -
# same pattern as telegram_common.py's _TOKEN_URL_RE. Used as a
# defense-in-depth scrub on any text that might end up printed; the
# primary defense is simply never printing a raw exception message or a
# request URL in the first place (see Get-TelegramErrorDescription below).
$Script:TelegramTokenRegex = 'bot\d+:[A-Za-z0-9_-]+'

function Get-RedactedText {
    <#
    .SYNOPSIS
        Replace any Telegram bot-token-shaped substring in $Text with a
        placeholder. Safe to call on arbitrary text - a no-op when no
        token-shaped substring is present. Mirrors
        telegram_common.py's redact_secrets().
    #>
    param([Parameter(Mandatory = $false)][AllowNull()][AllowEmptyString()][string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return "" }
    return [regex]::Replace($Text, $Script:TelegramTokenRegex, 'bot<redacted>')
}

function Read-DotEnv {
    <#
    .SYNOPSIS
        Tiny manual .env parser: KEY=VALUE per line, '#' comments, no deps.
        Mirrors bot.py/daily_report.py/email_monitor.py's parse_env_file()
        and the .sh scripts' `source "$ENV_FILE"` behavior (KEY=VALUE
        lines, blank/'#'-led lines skipped, an inline " #comment" trimmed,
        and matching surrounding quotes stripped) - same contract, ported.
    .OUTPUTS
        [hashtable] of string keys to string values. Missing file returns
        an empty hashtable (never throws) - callers check for required
        keys themselves, same as the .sh scripts' own missing-.env checks.
    #>
    param([Parameter(Mandatory = $true)][string]$Path)

    $values = @{}
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $values
    }

    $lines = Get-Content -LiteralPath $Path -Encoding UTF8
    foreach ($rawLine in $lines) {
        $line = $rawLine.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith('#')) { continue }

        $eqIndex = $line.IndexOf('=')
        if ($eqIndex -lt 0) { continue }

        $key = $line.Substring(0, $eqIndex).Trim()
        $value = $line.Substring($eqIndex + 1).Trim()

        # Strip an inline comment that follows a '#' preceded by whitespace
        # (matches the Python/.sh " #" convention exactly).
        $commentIndex = $value.IndexOf(' #')
        if ($commentIndex -ge 0) {
            $value = $value.Substring(0, $commentIndex).Trim()
        }

        # Strip matching surrounding quotes, if present.
        if ($value.Length -ge 2 -and $value[0] -eq $value[$value.Length - 1] -and
            ($value[0] -eq "'" -or $value[0] -eq '"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        $values[$key] = $value
    }
    return $values
}

function Get-TelegramApiBase {
    <#
    .SYNOPSIS
        Resolve the Telegram Bot API base URL: TELEGRAM_API_BASE from .env
        if set, else the real Telegram API. Windows-path-only override -
        the .sh scripts in this directory do NOT read this variable (see
        SETUP.md "Windows (Task Scheduler)" for why: they must stay
        byte-identical to their pre-Windows-support form).
    #>
    param([Parameter(Mandatory = $true)][hashtable]$EnvVars)
    $base = $EnvVars['TELEGRAM_API_BASE']
    if ([string]::IsNullOrEmpty($base)) {
        return $Script:TelegramDefaultApiBase
    }
    return $base.TrimEnd('/')
}

function Write-BridgeError {
    <#
    .SYNOPSIS
        Print a one-line "Error: <message>" to stderr and exit 1 - the
        same unconfigured-bridge / real-failure contract every .sh script
        in this directory already uses (missing .env, missing token/chat
        id, a real Telegram API error all exit 1 with a clear message).
        $Message must never itself contain the raw bot token or a full
        request URL - see the module docstring's CREDENTIAL HANDLING note.
    #>
    param([Parameter(Mandatory = $true)][string]$Message)
    [Console]::Error.WriteLine("Error: " + $Message)
    exit 1
}

function Get-TelegramErrorDescription {
    <#
    .SYNOPSIS
        Best-effort extraction of "(HTTP <code>: <description>)" from a
        failed Invoke-RestMethod call's ErrorRecord, WITHOUT ever touching
        $ErrorRecord.Exception.Message directly (that message can embed
        the full request URL, including the bot token, on both Windows
        PowerShell 5.1's WebException and PowerShell 7's
        HttpResponseException - see the module docstring). Only the parsed
        HTTP status code and Telegram's own `description` JSON field
        (never secret) are ever surfaced.
    .OUTPUTS
        [string] - empty string if nothing could be recovered, otherwise
        " (HTTP <code>: <description>)" or a subset of that.
    #>
    param([Parameter(Mandatory = $true)]$ErrorRecord)

    $statusCode = $null
    $bodyText = $null

    try {
        if ($ErrorRecord.Exception.Response) {
            $resp = $ErrorRecord.Exception.Response
            # PowerShell 7 / .NET Core: System.Net.Http.HttpResponseMessage.
            if ($resp.PSObject.Properties.Name -contains 'StatusCode') {
                try { $statusCode = [int]$resp.StatusCode } catch { }
            }
        }
    } catch { }

    # PowerShell 7's Invoke-RestMethod captures the response body on
    # HttpResponseException into $ErrorRecord.ErrorDetails.Message.
    try {
        if ($ErrorRecord.ErrorDetails -and $ErrorRecord.ErrorDetails.Message) {
            $bodyText = $ErrorRecord.ErrorDetails.Message
        }
    } catch { }

    # Windows PowerShell 5.1 (.NET Framework): System.Net.HttpWebResponse -
    # the body must be read from its response stream explicitly; it is
    # never present in ErrorDetails there.
    if (-not $bodyText) {
        try {
            $resp = $ErrorRecord.Exception.Response
            if ($resp -and ($resp.GetType().FullName -eq 'System.Net.HttpWebResponse')) {
                if (-not $statusCode) {
                    try { $statusCode = [int]$resp.StatusCode } catch { }
                }
                $stream = $resp.GetResponseStream()
                if ($stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    $bodyText = $reader.ReadToEnd()
                    $reader.Close()
                }
            }
        } catch { }
    }

    $description = $null
    if ($bodyText) {
        try {
            $parsed = $bodyText | ConvertFrom-Json
            if ($parsed.PSObject.Properties.Name -contains 'description') {
                $description = $parsed.description
            }
        } catch { }
    }

    if ($statusCode -and $description) {
        return " (HTTP ${statusCode}: ${description})"
    } elseif ($statusCode) {
        return " (HTTP ${statusCode})"
    } elseif ($description) {
        return " (${description})"
    }
    return ""
}

function Assert-BridgeConfigured {
    <#
    .SYNOPSIS
        Require .env, TELEGRAM_BOT_TOKEN, AND TELEGRAM_CHAT_ID, exiting 1
        with the same wording notify.sh/typing.sh/send-file.sh use if
        anything is missing. Returns the parsed env hashtable on success.

        Used by notify.ps1, typing.ps1, and send-file.ps1 - all three
        always require both variables unconditionally (matching their .sh
        counterparts exactly, including notify.sh requiring
        TELEGRAM_CHAT_ID even on its --group path, where the value is
        immediately overwritten - see notify.sh's own source).

        react.ps1 and register-commands.ps1 do NOT use this helper: each
        has its own required-variable shape (react.sh's TELEGRAM_CHAT_ID
        is optional given --chat, with a check ORDER and per-check message
        that this one-size-fits-all helper can't reproduce exactly;
        register-commands.sh needs only TELEGRAM_BOT_TOKEN, never
        TELEGRAM_CHAT_ID at all) - see the "config" section near the top of
        each of those two scripts for their inlined, script-exact checks.
    #>
    param([Parameter(Mandatory = $true)][string]$ScriptDir)

    $envFile = Join-Path $ScriptDir ".env"
    if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
        Write-BridgeError ".env not found at $envFile`n  Copy .env.example to .env and fill in TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID."
    }

    $envVars = Read-DotEnv -Path $envFile
    $token = $envVars['TELEGRAM_BOT_TOKEN']
    $chatId = $envVars['TELEGRAM_CHAT_ID']
    if ([string]::IsNullOrEmpty($token) -or [string]::IsNullOrEmpty($chatId)) {
        Write-BridgeError "TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID not set in $envFile"
    }

    return $envVars
}

function Invoke-TelegramForm {
    <#
    .SYNOPSIS
        POST an application/x-www-form-urlencoded request to a Telegram
        Bot API method and return the parsed JSON response, exiting 1 via
        Write-BridgeError on any transport failure or an {"ok":false,...}
        response body - the same two-stage check (request succeeded, then
        body says ok:true) every .sh script here already performs.
    .PARAMETER Method
        Bot API method name, e.g. "sendMessage" (no leading slash).
    .PARAMETER Body
        Hashtable of form fields (chat_id, text, etc.).
    #>
    param(
        [Parameter(Mandatory = $true)][string]$ApiBase,
        [Parameter(Mandatory = $true)][string]$Token,
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][hashtable]$Body,
        [int]$TimeoutSec = 30
    )

    $uri = "$ApiBase/bot$Token/$Method"
    # Invoke-WebRequest (not Invoke-RestMethod) so the raw response body
    # text is always available for the error message below, matching the
    # .sh twins' `grep -q '"ok":true' <<< "$RESPONSE"` / `... $RESPONSE`
    # wording exactly, including for a 200 whose body isn't JSON at all -
    # Invoke-RestMethod would instead silently content-type-sniff a body
    # like `<html>...</html>` into an XmlDocument, losing the original text.
    try {
        $webResponse = Invoke-WebRequest -Uri $uri -Method Post -Body $Body -UseBasicParsing -TimeoutSec $TimeoutSec
    } catch {
        # Match notify.sh/react.sh/send-file.sh's "Error: curl request to
        # Telegram API failed." wording exactly (with the one documented
        # substitution, "curl request" -> "request") - no HTTP-detail
        # suffix, so the first stderr line is byte-for-byte identical.
        Write-BridgeError "request to Telegram API failed."
    }
    $bodyText = $webResponse.Content

    # A 200 response with a non-JSON body (e.g. an HTML page from a proxy
    # sitting in front of the real API) means $response below stays $null -
    # under StrictMode, $response.ok on $null throws an unhandled
    # PropertyNotFoundException instead of the intended error path. Check
    # the property exists before reading it, same as the .sh twins never
    # assume the body parses at all.
    $response = $null
    try { $response = $bodyText | ConvertFrom-Json } catch { }
    $hasOk = $false
    try { $hasOk = ($response -and ($response.PSObject.Properties.Name -contains 'ok')) } catch { }
    if (-not $hasOk) {
        Write-BridgeError "Telegram API returned an error response: $bodyText"
    }

    if (-not $response.ok) {
        # Print the whole raw body, matching the .sh twins' `... $RESPONSE`
        # wording exactly - not just Telegram's (possibly empty)
        # `description` field.
        Write-BridgeError "Telegram API returned an error response: $bodyText"
    }

    return $response
}
