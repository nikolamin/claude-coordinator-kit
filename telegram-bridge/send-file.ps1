<#
.SYNOPSIS
    send-file.ps1 - Windows PowerShell port of send-file.sh. Deliver a file
    to Telegram, picking sendPhoto/sendAnimation/sendVideo/sendDocument
    from its extension.

.DESCRIPTION
    Same contract as send-file.sh:
        .\send-file.ps1 <path> [caption]

    Extension routing (identical to send-file.sh's resolve_send_method()):
        .jpg .jpeg .png .webp               -> sendPhoto      (falls back to
                                                sendDocument over Telegram's
                                                ~10MB photo limit)
        .gif                                 -> sendAnimation
        .mp4 .mov .mkv .webm .m4v .avi .3gp  -> sendVideo
        everything else                      -> sendDocument

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from a .env file located
    next to this script (NOT the caller's working directory) - same
    resolution as notify.ps1.

    Multipart upload is implemented directly against
    System.Net.Http.HttpClient / MultipartFormDataContent (not
    Invoke-RestMethod -Form, which is PowerShell 7-only) so this one
    implementation is written for both Windows PowerShell 5.1 and
    PowerShell 7+ (pwsh); exercised under PowerShell 7 against a stub API,
    not yet under 5.1 or on a real Windows host.

.EXIT CODES
    0 on success. 1 on any failure (bad usage, missing/unreadable file,
    over Telegram's ~50MB bot-upload cap, a real Telegram API error) -
    matches send-file.sh exactly.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
if ([string]::IsNullOrEmpty($ScriptDir)) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

. (Join-Path $ScriptDir "telegram_common.ps1")

# Telegram Bot API limits (see https://core.telegram.org/bots/api#sendphoto
# and the general file-upload note) - identical values to send-file.sh.
$PhotoMaxBytes = 10 * 1024 * 1024
$UploadMaxBytes = 50 * 1024 * 1024

function Resolve-SendMethod {
    <#
    .SYNOPSIS
        Pure function (no I/O): given a lowercase extension (no leading
        dot) and a file size in bytes, returns @{ Method = "<Bot API
        method>"; Field = "<multipart field name>" } - mirrors
        send-file.sh's resolve_send_method() exactly.
    #>
    param([Parameter(Mandatory = $true)][string]$Ext, [Parameter(Mandatory = $true)][long]$Bytes)

    # -CaseSensitive: send-file.sh's own resolve_send_method() is
    # case-sensitive (its own test_caller_must_lowercase_first asserts an
    # uppercase "JPG" falls through to sendDocument, NOT sendPhoto) - the
    # caller below already lowercases before calling this function, but
    # the function itself stays case-sensitive to match that contract
    # exactly, independent of what any future caller does.
    switch -CaseSensitive ($Ext) {
        { $_ -in @('jpg', 'jpeg', 'png', 'webp') } {
            if ($Bytes -gt $PhotoMaxBytes) {
                return @{ Method = "sendDocument"; Field = "document" }
            }
            return @{ Method = "sendPhoto"; Field = "photo" }
        }
        'gif' { return @{ Method = "sendAnimation"; Field = "animation" } }
        { $_ -in @('mp4', 'mov', 'mkv', 'webm', 'm4v', 'avi', '3gp') } {
            return @{ Method = "sendVideo"; Field = "video" }
        }
        default { return @{ Method = "sendDocument"; Field = "document" } }
    }
}

function Send-TelegramFile {
    <#
    .SYNOPSIS
        Multipart-POST $FilePath to a Telegram Bot API method, using
        System.Net.Http.HttpClient directly (works on both Windows
        PowerShell 5.1 and PowerShell 7+; Invoke-RestMethod -Form is
        PS7-only). Returns @{ StatusCode = <int>; Body = "<raw response
        text>" } - never throws for an HTTP-level failure (only for a
        transport-level one, e.g. DNS failure), matching how
        Invoke-TelegramForm's callers already expect two-stage checking.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][hashtable]$FormFields,
        [Parameter(Mandatory = $true)][string]$FileField,
        [Parameter(Mandatory = $true)][string]$FilePath
    )

    Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue

    # TLS 1.2: on Windows PowerShell 5.1 (.NET Framework) this HttpClient's
    # default handler honors [Net.ServicePointManager]::SecurityProtocol,
    # set once at telegram_common.ps1 load time (dot-sourced above this
    # script's own code); on PowerShell 7 (.NET Core) the OS negotiates TLS
    # and ServicePointManager plays no role here, so nothing else is needed.
    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromSeconds(300)
    $content = New-Object System.Net.Http.MultipartFormDataContent
    $fileStream = $null
    try {
        foreach ($key in $FormFields.Keys) {
            $stringContent = New-Object System.Net.Http.StringContent([string]$FormFields[$key])
            $content.Add($stringContent, $key)
        }

        $fileStream = [System.IO.File]::OpenRead($FilePath)
        $fileContent = New-Object System.Net.Http.StreamContent($fileStream)
        $fileName = [System.IO.Path]::GetFileName($FilePath)
        $content.Add($fileContent, $FileField, $fileName)

        $task = $client.PostAsync($Uri, $content)
        $response = $task.GetAwaiter().GetResult()
        $bodyTask = $response.Content.ReadAsStringAsync()
        $bodyText = $bodyTask.GetAwaiter().GetResult()

        return @{ StatusCode = [int]$response.StatusCode; Body = $bodyText }
    } finally {
        if ($fileStream) { $fileStream.Dispose() }
        $content.Dispose()
        $client.Dispose()
    }
}

# --- argument parsing -------------------------------------------------------
$filePath = $null
$caption = ""
if ($args.Count -ge 1) { $filePath = $args[0] }
if ($args.Count -ge 2) { $caption = [string]$args[1] }

if ([string]::IsNullOrEmpty($filePath)) {
    Write-BridgeError "usage: send-file.ps1 <path> [caption]`n  A file path is required as the first argument."
}

if (-not (Test-Path -LiteralPath $filePath)) {
    Write-BridgeError "file not found: $filePath"
}

$item = Get-Item -LiteralPath $filePath
if ($item.PSIsContainer) {
    Write-BridgeError "not a regular file: $filePath"
}

try {
    $testStream = [System.IO.File]::OpenRead($item.FullName)
    $testStream.Close()
} catch {
    Write-BridgeError "file not readable: $filePath"
}

$bytes = $item.Length
if ($bytes -gt $UploadMaxBytes) {
    Write-BridgeError "$filePath is $bytes bytes - over Telegram's ~50MB bot-upload cap. Not sent.`n  Split it into smaller pieces, or transfer it to the founder's device directly."
}

$extRaw = [System.IO.Path]::GetExtension($item.Name)
$extLower = ""
if (-not [string]::IsNullOrEmpty($extRaw) -and $extRaw.StartsWith('.')) {
    $extLower = $extRaw.Substring(1).ToLowerInvariant()
}

$routing = Resolve-SendMethod -Ext $extLower -Bytes $bytes

# --- config ------------------------------------------------------------------
$envVars = Assert-BridgeConfigured -ScriptDir $ScriptDir
$token = $envVars['TELEGRAM_BOT_TOKEN']
$chatId = $envVars['TELEGRAM_CHAT_ID']
$apiBase = Get-TelegramApiBase -EnvVars $envVars

# --- send ----------------------------------------------------------------
$formFields = @{ chat_id = $chatId }
if (-not [string]::IsNullOrEmpty($caption)) {
    $formFields['caption'] = $caption
}

$uri = "$apiBase/bot$token/$($routing.Method)"
$result = $null
try {
    $result = Send-TelegramFile -Uri $uri -FormFields $formFields -FileField $routing.Field -FilePath $item.FullName
} catch {
    # Transport-level failure (DNS, connection refused, etc.) - never print
    # $_.Exception.Message raw, since HttpClient exceptions can echo the
    # request URI (which embeds the token); redact defensively regardless.
    $safe = Get-RedactedText -Text $_.Exception.Message
    Write-BridgeError "request to Telegram API failed. $safe"
}

# send-file.sh's curl call uses --fail, so curl itself already fails (and
# never looks at the body) on ANY non-2xx HTTP status, not only a
# transport-level failure - HttpClient.PostAsync above does not do this on
# its own (it only throws for a real transport failure), so mirror --fail
# explicitly: a non-2xx status is "request failed", the same as .sh, not a
# {"ok":false,...} body to extract a description from.
if ($result.StatusCode -lt 200 -or $result.StatusCode -ge 300) {
    Write-BridgeError "request to Telegram API failed."
}

$parsed = $null
try { $parsed = $result.Body | ConvertFrom-Json } catch { }

# See telegram_common.ps1's Invoke-TelegramForm for why this guard exists:
# a 2xx body that isn't JSON (or isn't an object with an "ok" property)
# must not reach $parsed.ok directly - that throws under StrictMode.
$hasOk = $false
try { $hasOk = ($parsed -and ($parsed.PSObject.Properties.Name -contains 'ok')) } catch { }
if (-not $hasOk) {
    Write-BridgeError "Telegram API returned an unparseable response (HTTP $($result.StatusCode))."
}

if (-not $parsed.ok) {
    $desc = ""
    try { $desc = $parsed.description } catch { }
    Write-BridgeError "Telegram API returned an error response: $desc"
}

exit 0
