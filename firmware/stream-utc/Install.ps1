param([switch]$BuildOnly, [switch]$SkipBackup)
$ErrorActionPreference = 'Stop'
$board = 'esp32:esp32:XIAO_ESP32S3:PSRAM=opi,CDCOnBoot=default'
$sketch = Join-Path $PSScriptRoot 'XiaoStream'

function Find-ArduinoCli {
    $cmd = Get-Command arduino-cli.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($base in @($env:ProgramFiles, (Join-Path $env:LOCALAPPDATA 'Programs'))) {
        $path = Join-Path $base 'Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe'
        if (Test-Path -LiteralPath $path) { return $path }
    }
    throw 'Install Arduino IDE 2 or add arduino-cli.exe to PATH.'
}

try {
    $cli = Find-ArduinoCli
    $build = Join-Path $env:TEMP ('XiaoStream-build-' + [guid]::NewGuid().ToString('N'))
    Write-Host 'Compiling Stream Field Trial 03 for the XIAO ESP32-S3. Install RadioLib 8.0.0 in Library Manager.'
    & $cli compile --fqbn $board --output-dir $build $sketch
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed. See the first compiler error above. Use the Espressif esp32 board package 4.0.0 in Arduino IDE Boards Manager.' }
    $app = Join-Path $build 'XiaoStream.ino.bin'
    if (!(Test-Path -LiteralPath $app)) { throw 'Compiler did not produce the application image.' }
    Write-Host "Build succeeded.  Images are in $build"
    if ($BuildOnly) { exit 0 }
    & $cli board list
    $port = (Read-Host 'Enter the COM port of the new experimental XIAO').Trim().ToUpperInvariant()
    if ($port -notmatch '^COM[0-9]+$') { throw 'Expected a Windows COM port such as COM12.' }
    Write-Host "The firmware on $port will be replaced. Close serial monitors first."
    $action = 'back up and flash'
    if ($SkipBackup) { $action = 'flash WITHOUT saving a backup of' }
    if ((Read-Host "Type $port again to $action this board").Trim().ToUpperInvariant() -ne $port) { throw 'Installation cancelled.' }
    $backup = $null
    if (!$SkipBackup) {
        $toolDir = Join-Path $env:LOCALAPPDATA 'Arduino15\packages\esp32\tools\esptool_py'
        $tool = Get-ChildItem -Path "$toolDir\5*\esptool.exe" -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
        if (!$tool) { throw 'Could not find the Arduino esptool 5 executable used for the flash backup.' }
        $backup = & (Join-Path $PSScriptRoot 'Backup-Flash.ps1') -Tool $tool -Port $port -Directory (Join-Path $PSScriptRoot 'Backups')
    }
    & $cli upload --fqbn $board --port $port --input-dir $build $sketch
    if ($LASTEXITCODE -ne 0) {
        if ($backup) { throw "Upload failed. Your verified backup is in $backup" }
        throw 'Upload failed. This run was started with -SkipBackup. See the upload error above.'
    }
    Write-Host 'Upload complete. Open Serial Monitor at 115200 and send status, then clip, with Newline.'
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
