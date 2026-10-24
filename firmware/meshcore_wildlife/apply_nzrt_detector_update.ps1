param(
  [string]$Project = "$env:USERPROFILE\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor",
  [string]$Port = "COM8"
)
$ErrorActionPreference = "Stop"
Write-Host "NZRT MeshCore field pilot daily clock and daytime mic standby update"
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
$files = @("WildlifeMic.cpp","WildlifeMic.h","WildlifeDetector.cpp","WildlifeDetector.h","WildlifeTime.cpp","WildlifeTime.h","WildlifeDay.cpp","WildlifeDay.h")
$downloads = @{}
try {
  foreach ($name in $files) {
    $target = Join-Path $Project "nzrt\$name"
    if ($name -notlike "WildlifeTime.*" -and $name -notlike "WildlifeDay.*" -and -not (Test-Path -LiteralPath $target -PathType Leaf)) {throw "Missing NZRT source $target"}
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
  if (-not $mic.Contains("NZRT-FIELD-PILOT-4") -or -not $mic.Contains("WildlifeTime::epochForUptime")) {
    throw "Downloaded microphone does not auto-enable DSP or match FIELD-PILOT-4"
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


  # Additional non-blocking time bridge, powered on only at startup.
  # Input bytes after 'nzrt wifi set ' must NOT be echoed to the USB terminal.
  function Replace-Once([string]$Text,[string]$Old,[string]$New,[string]$Label) {
    if (-not $Text.Contains($Old)) {throw "Could not patch $Label in local project. No files replaced."}
    return $Text.Replace($Old,$New)
  }
  if (-not $src.Contains('#include "WildlifeTime.h"')) {
    $src = Replace-Once $src '#include "WildlifeMic.h"' ('#include "WildlifeMic.h"' + "`n" + '#include "WildlifeTime.h"') "time header"
  }
  if (-not $src.Contains('#include "WildlifeDay.h"')) {
    $src = Replace-Once $src '#include "WildlifeTime.h"' ('#include "WildlifeTime.h"' + "`n" + '#include "WildlifeDay.h"') "day scheduler header"
  }
  if (-not $src.Contains("WildlifeTime::begin(rtc_clock)")) {
    $src = Replace-Once $src 'Serial.println("NZRT microphone start failed: MeshCore still running");' ("Serial.println(" + '"NZRT microphone start failed: MeshCore still running"' + ");`n  WildlifeTime::begin(rtc_clock);") "time startup"
  }
  if (-not $src.Contains("WildlifeDay::begin()")) {
    $src = Replace-Once $src "  WildlifeTime::begin(rtc_clock);" "  WildlifeTime::begin(rtc_clock);`n  WildlifeDay::begin();" "day scheduler startup"
  }
  if (-not $src.Contains("WildlifeTime::tick(rtc_clock)")) {
    $src = Replace-Once $src "  rtc_clock.tick();" "  rtc_clock.tick();`n  WildlifeTime::tick(rtc_clock);" "time loop"
  }
  if (-not $src.Contains("WildlifeDay::tick()")) {
    $src = Replace-Once $src "  WildlifeTime::tick(rtc_clock);" "  WildlifeTime::tick(rtc_clock);`n  WildlifeDay::tick();" "day scheduler loop"
  }
  if (-not $src.Contains('strcmp(command, "nzrt time")')) {
    $oldCommands=@'
    } else if (strcmp(command, "nzrt dsp off") == 0) {
      WildlifeMic::setDspEnabled(false);
    } else {
'@
    $newCommands=@'
    } else if (strcmp(command, "nzrt dsp off") == 0) {
      WildlifeMic::setDspEnabled(false);
    } else if (strcmp(command, "nzrt time") == 0) {
      WildlifeTime::printStatus();
    } else if (strncmp(command, "nzrt wifi set ", 14) == 0) {
      WildlifeTime::configureWiFi(command + 14);
    } else if (strcmp(command, "nzrt wifi clear") == 0) {
      WildlifeTime::clearWiFi();
    } else {
'@
    $src = Replace-Once $src $oldCommands $newCommands "local time CLI"
  }
  if (-not $src.Contains('strcmp(command, "nzrt day")')) {
    $oldDay=@'
    } else if (strcmp(command, "nzrt wifi clear") == 0) {
      WildlifeTime::clearWiFi();
    } else {
'@
    $newDay=@'
    } else if (strcmp(command, "nzrt wifi clear") == 0) {
      WildlifeTime::clearWiFi();
    } else if (strcmp(command, "nzrt day") == 0) {
      WildlifeDay::printStatus();
    } else if (strcmp(command, "nzrt day test sleep") == 0) {
      WildlifeDay::testSleep();
    } else if (strcmp(command, "nzrt day test wake") == 0) {
      WildlifeDay::testWake();
    } else if (strcmp(command, "nzrt day auto") == 0) {
      WildlifeDay::autoMode();
    } else if (strcmp(command, "nzrt day enable") == 0) {
      WildlifeDay::setScheduleEnabled(true);
    } else if (strcmp(command, "nzrt day disable") == 0) {
      WildlifeDay::setScheduleEnabled(false);
    } else {
'@
    $src = Replace-Once $src $oldDay $newDay "day CLI"
  }
  if (-not $src.Contains('strncmp(command, "nzrt wifi set ", 14) != 0')) {
    $src = Replace-Once $src "      Serial.print(c);" '      if (strncmp(command, "nzrt wifi set ", 14) != 0) Serial.print(c);' "secret-free USB echo"
  }
  $localText = [IO.File]::ReadAllText($localIni)
  if (-not $localText.Contains("+<../nzrt/WildlifeTime.cpp>")) {
    $localText = Replace-Once $localText "+<../nzrt/WildlifeDetector.cpp>" "+<../nzrt/WildlifeDetector.cpp>`n  +<../nzrt/WildlifeTime.cpp>" "PlatformIO time source"
  }
  if (-not $localText.Contains("+<../nzrt/WildlifeDay.cpp>")) {
    $localText = Replace-Once $localText "+<../nzrt/WildlifeTime.cpp>" "+<../nzrt/WildlifeTime.cpp>`n  +<../nzrt/WildlifeDay.cpp>" "PlatformIO day source"
  }
  $updateMain = $true

  # Backup the exact currently installed source before modifying it.
  $backup = Join-Path $Project ("nzrt_backup_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  foreach ($name in $files) {
    $target = Join-Path $Project "nzrt\$name"
    if (Test-Path -LiteralPath $target) {
      Copy-Item -LiteralPath $target -Destination (Join-Path $backup $name)
    }
  }
  Copy-Item -LiteralPath $mainPath -Destination (Join-Path $backup "main.cpp")
  Copy-Item -LiteralPath $localIni -Destination (Join-Path $backup "platformio.local.ini")

  foreach ($name in $files) {
    $target = Join-Path $Project "nzrt\$name"
    Move-Item -LiteralPath $downloads[$name] -Destination $target -Force
    Write-Host "Updated $name"
  }
  if ($updateMain) {
    [IO.File]::WriteAllText($mainPath,$src,(New-Object System.Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($localIni,$localText,(New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Enabled UTC time bridge, sunrise/sunset daytime microphone standby and NTP build"
  }
  Write-Host "Source backup: $backup"
  Write-Host "Private admin password and radio configs unchanged; local.ini includes new UTC source."
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
Write-Host "SUCCESS: new build should print 'NZRT SESSION', report 'NZRT-FIELD-PILOT-4', and start DSP automatically."
Write-Host "Test serial with: py -m serial.tools.miniterm $Port 115200 --eol CR"
Write-Host "Use CLI: nzrt wifi set YOUR_SSID|YOUR_WIFI_PASSWORD  (stored in device NVS, not GitHub)"
Write-Host "Then reboot once. For status: nzrt time ; nzrt day ; nzrt status ; log"
Write-Host "BAT default: nzrt day enable ; ALWAYS ON: nzrt day disable (settings persist across reboot)"
Write-Host "Day mode test: nzrt day test sleep ; nzrt day test wake ; nzrt day auto"
Write-Host "NOTE: this stops microphone I2S/DSP by day. The ESP32 and MeshCore LoRa remain awake."
Write-Host "No Wi-Fi configured? Start remains UNSYNCED; MeshCore's authenticated remote 'clock sync' is a fallback."
