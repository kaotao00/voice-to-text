$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $PSCommandPath
$pythonExe = Join-Path $env:USERPROFILE "miniconda3\envs\voice\python.exe"
$voiceScript = Join-Path $appDir "voice_to_text.py"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    exit 1
}

while ($true) {
    $codexRunning = @(Get-Process -Name "codex" -ErrorAction SilentlyContinue).Count -gt 0
    $voiceRunning = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq "python.exe" -and $_.CommandLine -like "*voice_to_text.py*" }).Count -gt 0

    if ($codexRunning -and -not $voiceRunning) {
        Start-Process -FilePath $pythonExe -ArgumentList "voice_to_text.py" -WorkingDirectory $appDir -WindowStyle Hidden
    }

    Start-Sleep -Seconds 3
}
