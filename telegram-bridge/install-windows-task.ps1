<#
.SYNOPSIS
    install-windows-task.ps1 - Register the Telegram bridge as Windows
    Task Scheduler tasks: the always-on bot loop (bot.py) and, optionally,
    the daily activity digest (daily_report.py) - the Windows equivalent of
    the launchd .plist.template / systemd .service+.timer.template pair
    documented in SETUP.md.

.DESCRIPTION
    bot.py runs exactly ONE poll cycle per process invocation and exits
    (see SETUP.md (f)) - "keep polling forever" is provided by an OS-level
    supervisor relaunching it immediately after every exit. On macOS/Linux
    that's launchd's KeepAlive=true / systemd's Restart=always. On Windows,
    this script builds the equivalent using a Task Scheduler trigger with
    an indefinite REPETITION pattern (fires once immediately on
    registration, then again every -PollIntervalSeconds indefinitely,
    self-healing after a reboot within one interval without needing a
    separate always-running process) PLUS an AtLogOn trigger so the loop
    also (re-)starts the moment the user logs on. MultipleInstances is set
    to IgnoreNew so the two triggers can never launch overlapping copies -
    matches "only one getUpdates consumer per bot token at a time" (see
    SETUP.md Gotchas). RestartCount/RestartInterval additionally restart a
    crashed run - the Task Scheduler analogue of "restart on failure" -
    though the repeating trigger alone would already relaunch it within one
    interval regardless.

    daily_report.py is a plain scheduled one-shot (systemd's timer /
    launchd's StartCalendarInterval equivalent) - a single Daily trigger at
    -DailyReportTime, no repetition/restart needed since a single run
    either sends a digest or exits quickly.

    PYTHON INTERPRETER RESOLUTION (mirrors what the plist/service
    templates ask a human to do - fill in an ABSOLUTE interpreter path -
    see the "PATH gotcha" callout in SETUP.md and in this script's own
    header): resolved in this order, unless -PythonPath is given explicitly:
        1. -PythonPath, if passed.
        2. <BridgeDir>\venv\Scripts\python.exe, if it exists (the Windows
           equivalent of SETUP.md (b)'s optional `venv/bin/python3`).
        3. `python` resolved via Get-Command (its absolute .Source path).
        4. `py` (the Python Launcher for Windows) resolved via Get-Command.
    Always resolved to an ABSOLUTE path before being baked into the task
    action - Task Scheduler tasks inherit the user's environment at logon,
    but NOT any interactive-shell-only PATH additions (nvm/homebrew-style
    managers on Unix; a user's PowerShell-profile-only PATH edits on
    Windows) - the Windows analogue of the exact PATH gotcha SETUP.md
    already documents for launchd/systemd. An absolute path sidesteps it
    entirely, same fix, same reasoning, different OS.

    STDOUT/STDERR: both tasks run through `cmd.exe /c ... >> <logfile>
    2>&1`, since a Task Scheduler action's own -Execute must be a single
    executable/arguments pair with no shell redirection support - `cmd.exe
    /c` supplies the redirection shell, the way `sh -c` would on Unix. Logs
    land at <BridgeDir>\task-bot-stdout.log and
    <BridgeDir>\task-daily-report-stdout.log - alongside (not replacing)
    bot.py's own bot.log / daily_report.py's own daily_report.log, which
    are written via Python's logging module regardless of how the process
    was launched. This mirrors launchd's StandardOutPath/StandardErrorPath
    and systemd's journal capture: a place to see interpreter-startup
    failures that happen before Python's own logging is even configured.

.PARAMETER BridgeDir
    Absolute path to this telegram-bridge\ directory. Defaults to the
    directory this script lives in.

.PARAMETER PythonPath
    Absolute path to python.exe. See PYTHON INTERPRETER RESOLUTION above
    for the auto-detection order used when this is omitted.

.PARAMETER PollIntervalSeconds
    How often the repeating trigger re-fires bot.py. Default 60 - bot.py's
    own poll cycle (a ~25s Telegram long-poll plus overhead) comfortably
    finishes within that window in the common case; MultipleInstances =
    IgnoreNew means a poll cycle that runs long simply skips that tick
    rather than overlapping.

.PARAMETER DailyReportTime
    Local time-of-day (HH:mm, 24h) the daily digest task runs at. Default
    "08:00" - matches the plist/service templates' own default.

.PARAMETER SkipDailyReport
    Skip registering the daily-digest task entirely - matches SETUP.md
    (k)'s "optional, skip it if you don't want it."

.PARAMETER BotTaskName
    Task Scheduler task name for the bot loop. Default
    "ClaudeTelegramBridge".

.PARAMETER DailyReportTaskName
    Task Scheduler task name for the daily digest. Default
    "ClaudeTelegramBridgeDailyReport".

.PARAMETER Uninstall
    Remove both tasks (if present) instead of installing them. Every other
    parameter above except the two *TaskName parameters and -BridgeDir is
    ignored in this mode.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install-windows-task.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install-windows-task.ps1 -Uninstall

.NOTES
    Requires the ScheduledTasks module (ships with Windows; works
    unmodified under both Windows PowerShell 5.1 and PowerShell 7+ on
    Windows - it is a CDXML module, not a compiled binary module, so PS7
    loads it natively with no compatibility shim). Must be run from an
    elevated OR a normal user PowerShell session - registering a task that
    runs as the CURRENT user (this script's default) does not require
    admin rights.
#>

[CmdletBinding()]
param(
    [string]$BridgeDir,
    [string]$PythonPath,
    [int]$PollIntervalSeconds = 60,
    [string]$DailyReportTime = "08:00",
    [switch]$SkipDailyReport,
    [string]$BotTaskName = "ClaudeTelegramBridge",
    [string]$DailyReportTaskName = "ClaudeTelegramBridgeDailyReport",
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrEmpty($BridgeDir)) {
    $BridgeDir = $PSScriptRoot
    if ([string]::IsNullOrEmpty($BridgeDir)) {
        $BridgeDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
}
$BridgeDir = (Resolve-Path -LiteralPath $BridgeDir).ProviderPath

Import-Module ScheduledTasks -ErrorAction Stop

# ---------------------------------------------------------------------------
# Uninstall path
# ---------------------------------------------------------------------------
if ($Uninstall) {
    foreach ($name in @($BotTaskName, $DailyReportTaskName)) {
        $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($existing) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Output "Removed scheduled task: $name"
        } else {
            Write-Output "No scheduled task named '$name' found; nothing to remove."
        }
    }
    exit 0
}

# ---------------------------------------------------------------------------
# Python interpreter resolution (see PYTHON INTERPRETER RESOLUTION above)
# ---------------------------------------------------------------------------
if ([string]::IsNullOrEmpty($PythonPath)) {
    $venvPython = Join-Path $BridgeDir "venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        $PythonPath = $venvPython
    } else {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) { $PythonPath = $cmd.Source }
    }
    if ([string]::IsNullOrEmpty($PythonPath)) {
        $cmd = Get-Command py -ErrorAction SilentlyContinue
        if ($cmd) { $PythonPath = $cmd.Source }
    }
    if ([string]::IsNullOrEmpty($PythonPath)) {
        [Console]::Error.WriteLine("Error: could not auto-detect a Python interpreter. Pass -PythonPath <absolute path to python.exe> explicitly (e.g. the output of 'py -c ""import sys; print(sys.executable)""'), or create a venv first: cd `"$BridgeDir`"; py -m venv venv; venv\Scripts\pip install requests")
        exit 1
    }
} else {
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        [Console]::Error.WriteLine("Error: -PythonPath does not point to an existing file: $PythonPath")
        exit 1
    }
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).ProviderPath

if (-not (Test-Path -LiteralPath (Join-Path $BridgeDir ".env") -PathType Leaf)) {
    Write-Warning "$BridgeDir\.env not found yet. Copy .env.example to .env and fill it in before (or right after) running this - both tasks will just log an error and exit each cycle until it exists. See SETUP.md."
}

Write-Output "Bridge directory: $BridgeDir"
Write-Output "Python interpreter: $PythonPath"

$currentUser = "$env:USERDOMAIN\$env:USERNAME"

# ---------------------------------------------------------------------------
# Bot loop task
# ---------------------------------------------------------------------------
$botLogFile = Join-Path $BridgeDir "task-bot-stdout.log"
# cmd.exe /c supplies the shell-redirection this action needs (Task
# Scheduler's own -Execute/-Argument pair has no built-in redirection) -
# the Windows analogue of the "sh -c '... >> log 2>&1'" pattern.
$botCmdArgument = '/c ""' + $PythonPath + '" "' + (Join-Path $BridgeDir "bot.py") + '" >> "' + $botLogFile + '" 2>&1"'
$botAction = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $botCmdArgument -WorkingDirectory $BridgeDir

# Trigger 1: fire once, immediately (start time in the past), then repeat
# every $PollIntervalSeconds indefinitely. New-ScheduledTaskTrigger's own
# -RepetitionDuration parameter requires a finite value; setting the
# underlying Repetition.Duration CIM property to an empty string directly
# (after creating the trigger) is the documented way to get "repeat
# indefinitely" instead - the Task Scheduler XML schema treats an absent/
# empty <Duration> under <Repetition> as "no end", the same meaning
# launchd's unconditional KeepAlive=true and systemd's Restart=always both
# carry for bot.py's single-poll-cycle-per-invocation design.
$repeatingTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date)
$repeatingTrigger.Repetition.Interval = "PT" + [string]$PollIntervalSeconds + "S"
$repeatingTrigger.Repetition.Duration = ""
$repeatingTrigger.Repetition.StopAtDurationEnd = $false

# Trigger 2: also start (or restart) the loop the moment the user logs on,
# so a session that begins between repeating-trigger ticks doesn't wait up
# to $PollIntervalSeconds before the first poll cycle runs.
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn

$botSettings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# S4U: runs as the current user without storing a password and without
# requiring an interactive session to be open - the closest Windows
# equivalent to a launchd LaunchAgent / systemd --user service running
# detached from any particular login shell. Requires the account to hold
# "Log on as a batch job" rights, which Register-ScheduledTask grants
# automatically for the task's principal.
$botPrincipal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType S4U -RunLevel Limited

$existingBotTask = Get-ScheduledTask -TaskName $BotTaskName -ErrorAction SilentlyContinue
if ($existingBotTask) {
    Unregister-ScheduledTask -TaskName $BotTaskName -Confirm:$false
    Write-Output "Replaced existing task: $BotTaskName"
}

Register-ScheduledTask -TaskName $BotTaskName `
    -Action $botAction `
    -Trigger @($repeatingTrigger, $logonTrigger) `
    -Settings $botSettings `
    -Principal $botPrincipal `
    -Description "Claude Telegram bridge: relaunches bot.py every $PollIntervalSeconds s (one Telegram getUpdates poll cycle per run) plus on logon. Windows Task Scheduler equivalent of com.example.claude-telegram-bridge.plist.template / claude-telegram-bridge.service.template. See SETUP.md." `
    | Out-Null

Start-ScheduledTask -TaskName $BotTaskName
Write-Output "Installed and started scheduled task: $BotTaskName (repeats every ${PollIntervalSeconds}s; log: $botLogFile)"

# ---------------------------------------------------------------------------
# Daily report task (optional)
# ---------------------------------------------------------------------------
if (-not $SkipDailyReport) {
    $reportLogFile = Join-Path $BridgeDir "task-daily-report-stdout.log"
    $reportCmdArgument = '/c ""' + $PythonPath + '" "' + (Join-Path $BridgeDir "daily_report.py") + '" >> "' + $reportLogFile + '" 2>&1"'
    $reportAction = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $reportCmdArgument -WorkingDirectory $BridgeDir

    # Parse -DailyReportTime ("HH:mm", 24h) explicitly via InvariantCulture
    # rather than relying on New-ScheduledTaskTrigger's own implicit
    # string->DateTime coercion for -At, which goes through the CURRENT
    # user culture and could misread "08:00" on a non-US locale (e.g. one
    # where ':' or digit grouping parses differently).
    try {
        $reportTimeOfDay = [DateTime]::ParseExact(
            $DailyReportTime, 'HH:mm',
            [System.Globalization.CultureInfo]::InvariantCulture)
    } catch {
        [Console]::Error.WriteLine("Error: -DailyReportTime must be in 24h `"HH:mm`" form, e.g. `"08:00`" or `"20:30`" - got: $DailyReportTime")
        exit 1
    }
    $reportTrigger = New-ScheduledTaskTrigger -Daily -At $reportTimeOfDay

    $reportSettings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

    $reportPrincipal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType S4U -RunLevel Limited

    $existingReportTask = Get-ScheduledTask -TaskName $DailyReportTaskName -ErrorAction SilentlyContinue
    if ($existingReportTask) {
        Unregister-ScheduledTask -TaskName $DailyReportTaskName -Confirm:$false
        Write-Output "Replaced existing task: $DailyReportTaskName"
    }

    Register-ScheduledTask -TaskName $DailyReportTaskName `
        -Action $reportAction `
        -Trigger $reportTrigger `
        -Settings $reportSettings `
        -Principal $reportPrincipal `
        -Description "Claude Telegram bridge: daily git-activity digest (daily_report.py), once a day at $DailyReportTime local time. Windows Task Scheduler equivalent of com.example.claude-telegram-bridge-daily-report.plist.template / claude-telegram-bridge-daily-report.service.template + .timer.template. See SETUP.md section (k)." `
        | Out-Null

    Write-Output "Installed scheduled task: $DailyReportTaskName (daily at $DailyReportTime; log: $reportLogFile)"
} else {
    Write-Output "Skipped daily-report task (-SkipDailyReport)."
}

Write-Output ""
Write-Output "To uninstall: powershell -ExecutionPolicy Bypass -File install-windows-task.ps1 -Uninstall"
exit 0
