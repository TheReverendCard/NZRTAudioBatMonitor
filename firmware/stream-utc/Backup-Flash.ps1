param(
    [Parameter(Mandatory)][string]$Tool,
    [Parameter(Mandatory)][string]$Port,
    [Parameter(Mandatory)][string]$Directory
)
$ErrorActionPreference = 'Stop'
$flashSize = 8MB
$chunkSize = 256KB
$options = @('--chip', 'esp32s3', '--port', $Port, '--baud', '115200', '--after', 'no-reset-stub')

# Keep the application stopped while taking its snapshot. Each invocation can
# reset back into the bootloader independently after a lost connection.
$identity = & $Tool @options flash-id
if ($LASTEXITCODE -ne 0) { throw "Could not identify the XIAO on $Port. Check its port and USB connection." }
$identity | Out-Host
$report = $identity -join [Environment]::NewLine
if ($report -notmatch '(?im)^\s*MAC:\s*([0-9a-f]{2}(?::[0-9a-f]{2}){5})\b') {
    throw 'Could not identify the chip MAC for this backup.'
}
$chipId = $Matches[1].Replace(':', '').ToUpperInvariant()
if ($report -notmatch '(?im)Detected flash size:\s*8\s*MB\b') {
    throw 'This backup expects the 8 MB XIAO ESP32-S3. Check the detected size above.'
}
$partsDir = Join-Path $Directory "resume-$chipId"
[IO.Directory]::CreateDirectory($partsDir) | Out-Null
$lock = [IO.File]::Open((Join-Path $partsDir 'backup.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
    $parts = @()
    for ($offset = 0; $offset -lt $flashSize; $offset += $chunkSize) {
        $address = '0x{0:X6}' -f $offset
        $part = Join-Path $partsDir "$address.bin"
        $parts += $part
        if ([IO.File]::Exists($part) -and (Get-Item -LiteralPath $part).Length -eq $chunkSize) {
            Write-Host "Checking saved block at $address"
            & $Tool @options verify-flash $address $part | Out-Host
            if ($LASTEXITCODE -eq 0) { continue }
        }
        $complete = $false
        foreach ($attempt in 1..3) {
            Write-Host "Reading 256 KiB at $address (attempt $attempt of 3)"
            $temp = "$part.partial"
            if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) }
            & $Tool @options read-flash $address $chunkSize $temp | Out-Host
            if ($LASTEXITCODE -eq 0 -and [IO.File]::Exists($temp) -and (Get-Item -LiteralPath $temp).Length -eq $chunkSize) {
                Move-Item -LiteralPath $temp -Destination $part -Force
                $complete = $true
                break
            }
        }
        if (!$complete) {
            throw "Backup stopped at $address. Completed blocks are in $partsDir. Reconnect the same board and run Install.cmd from this folder to resume."
        }
    }

    $backup = Join-Path $Directory ('Xiao-{0}-{1}.bin' -f $chipId,(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    $output = [IO.File]::Open("$backup.partial", 'CreateNew', 'Write', 'None')
    try {
        foreach ($part in $parts) {
            $inputStream = [IO.File]::OpenRead($part)
            try { $inputStream.CopyTo($output) } finally { $inputStream.Dispose() }
        }
    } finally { $output.Dispose() }
    if ((Get-Item -LiteralPath "$backup.partial").Length -ne $flashSize) { throw 'Incomplete backup image.' }
    Write-Host 'Checking the assembled 8 MiB image against the flash on the XIAO.'
    & $Tool @options verify-flash 0 "$backup.partial" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Full-image verification failed. Upload stopped. Rerun Install.cmd to recheck the blocks and retry.' }
    Move-Item -LiteralPath "$backup.partial" -Destination $backup
    (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash | Set-Content -LiteralPath "$backup.sha256" -Encoding ASCII
    Write-Host "Verified backup saved to $backup"
    foreach ($part in $parts) { [IO.File]::Delete($part) }
    return $backup
} finally { $lock.Dispose() }
