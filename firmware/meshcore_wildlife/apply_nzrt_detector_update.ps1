param(
  [string]$Project = "$env:USERPROFILE\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor",
  [string]$Port = "COM8"
)
$ErrorActionPreference = "Stop"
Write-Host "NZRT MeshCore acoustic test update - USB-ISOLATE-2"
$localIni = Join-Path $Project "platformio.local.ini"
$mainPath = Join-Path $Project "examples\simple_repeater\main.cpp"
$variant = Join-Path $Project "variants\xiao_s3_wio\platformio.ini"
foreach ($check in @($localIni, $mainPath, $variant)) {
  if (-not (Test-Path -LiteralPath $check -PathType Leaf)) {
    throw "Unexpected PlatformIO project: missing $check"
  }
}
# Do not edit/read/show ADMIN_PASSWORD. Preserve the configured .ini files.
$root = "https://raw.githubusercontent.com/TheReverendCard/NZRTAudioBatMonitor/exp/meshcore-wildlife-repeater/firmware/meshcore_wildlife"
$files = @("WildlifeMic.cpp","WildlifeMic.h","WildlifeDetector.cpp","WildlifeDetector.h")
$downloads = @{}
try {
  foreach ($name in $files) {
    $target = Join-Path $Project "nzrt\$name"
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {throw "Missing NZRT source $target"}
    $temporary = "$target.download"
    Invoke-WebRequest -UseBasicParsing -Uri "$root/$name" -OutFile $temporary
    $downloads[$name] = $temporary
    Write-Host "Downloaded $name"
  }
  $detector = [IO.File]::ReadAllText($downloads["WildlifeDetector.cpp"])
  $mic = [IO.File]::ReadAllText($downloads["WildlifeMic.cpp"])
  if (-not $detector.Contains("onInputGap") -or -not $detector.Contains("taps[17]")) {
    throw "Downloaded detector is not the expected CIC16/17-tap version"
  }
  if (-not $mic.Contains("USB-ISOLATE-2")) {
    throw "Downloaded microphone is not the expected USB isolation build"
  }
  $src = [IO.File]::ReadAllText($mainPath).Replace("`r`n","`n")
  $old = @'
    if (strcmp(command, "nzrt status") == 0) {
      WildlifeMic::printStatus();
    } else {
      the_mesh.handleCommand(0, command, reply);  // NOTE: there is no sender_timestamp via serial!
    }
'@
  $new = @'
    if (strcmp(command, "nzrt status") == 0) {
      WildlifeMic::printStatus();
    } else if (strcmp(command, "nzrt dsp on") == 0) {
      WildlifeMic::setDspEnabled(true);
    } else if (strcmp(command, "nzrt dsp off") == 0) {
      WildlifeMic::setDspEnabled(false);
    } else {
      the_mesh.handleCommand(0, command, reply);  // NOTE: there is no sender_timestamp via serial!
    }
'@
  $old = $old.Replace("`r`n","`n")
  $new = $new.Replace("`r`n","`n")
  if (-not $src.Contains('strcmp(command, "nzrt dsp on")')) {
    if (-not $src.Contains($old)) {
      throw "Cannot safely locate prior 'nzrt status' handler in main.cpp. No files changed."
    }
    $src = $src.Replace($old,$new)
    $updateMain = $true
  } else {
    $updateMain = $false
  }

  # Backup the exact currently installed source before modifying it.
  $backup = Join-Path $Project ("nzrt_backup_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  foreach ($name in $files) {
    $target = Join-Path $Project "nzrt\$name"
    Copy-Item -LiteralPath $target -Destination (Join-Path $backup $name)
  }
  Copy-Item -LiteralPath $mainPath -Destination (Join-Path $backup "main.cpp")

  foreach ($name in $files) {
    $target = Join-Path $Project "nzrt\$name"
    Move-Item -LiteralPath $downloads[$name] -Destination $target -Force
    Write-Host "Updated $name"
  }
  if ($updateMain) {
    [IO.File]::WriteAllText($mainPath,$src,(New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Added 'nzrt dsp on/off' CLI handlers"
  }
  Write-Host "Source backup: $backup"
  Write-Host "Private admin password and all .ini files remain unchanged."
} finally {
  foreach ($name in $files) {
    if ($downloads.ContainsKey($name) -and (Test-Path -LiteralPath $downloads[$name])) {
      Remove-Item -LiteralPath $downloads[$name] -Force
    }
  }
}
Write-Host "Compiling and uploading to $Port ..."
& py -m platformio run -d $Project -e NZRT_Xiao_S3_WIO_wildlife_repeater -t upload --upload-port $Port
if ($LASTEXITCODE -ne 0) {throw "PlatformIO failed (exit code $LASTEXITCODE). Firmware was not confirmed uploaded."}
Write-Host "SUCCESS: new build should display 'USB-ISOLATE-2', then NZRT ALIVE every 10 seconds."
Write-Host "Test serial with: py -m serial.tools.miniterm $Port 115200 --eol CR"
Write-Host "If serial is stable, use: nzrt status ; nzrt dsp on ; nzrt status"
