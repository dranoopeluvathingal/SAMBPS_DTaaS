$intervalMinutes = 30
Write-Host "Starting SAMBPS Auto-Sync Pipeline..." -ForegroundColor Cyan
while($true) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    if (git status --porcelain) {
        Write-Host "[$timestamp] Syncing changes..." -ForegroundColor Yellow
        git add .
        git commit -m "Auto-sync: $timestamp"
        git push origin master
    } else {
        Write-Host "[$timestamp] No changes." -ForegroundColor Gray
    }
    Start-Sleep -Seconds ($intervalMinutes * 60)
}
