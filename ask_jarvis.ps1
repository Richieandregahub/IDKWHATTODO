param(
    [Parameter(Mandatory=$true, ValueFromRemainingArguments=$true)]
    [string[]]$Text
)

$text = ($Text -join ' ').Trim()
if (-not $text) { Write-Output "Usage: ask_jarvis.ps1 <what to say to Richie Jarvis>"; exit 1 }

$body = @{ text = $text } | ConvertTo-Json -Compress
try {
    $r = Invoke-RestMethod -Uri http://127.0.0.1:8765/command -Method Post `
        -ContentType 'application/json' -Body $body -TimeoutSec 60
    if ($r.speak) { Write-Output $r.speak } else { Write-Output ($r | ConvertTo-Json -Compress) }
} catch {
    Write-Output "Richie Jarvis server is not running. Start it first: C:\Users\bosssfrommars\Desktop\ai\jarvis\start_jarvis.bat"
}
