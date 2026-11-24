$socket = [Net.Sockets.UdpClient]::new(8768)
$peer = [Net.IPEndPoint]::new([Net.IPAddress]::Any, 0)
try {
    Write-Host 'Listening on UDP port 8768.  Press Ctrl+C to stop.'
    while ($true) {
        $data = $socket.Receive([ref]$peer)
        $message = [Text.Encoding]::UTF8.GetString($data)
        if ($message.StartsWith('XIAO-STREAM-01 ') -or $message.StartsWith('XIAO-STREAM-02 ')) {
            Write-Output ("{0:o} {1} {2}" -f [DateTime]::UtcNow, $peer.Address, $message)
        }
    }
} finally {
    $socket.Dispose()
}
