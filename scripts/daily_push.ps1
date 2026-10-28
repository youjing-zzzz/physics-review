# 每天收工：提交并推送到 GitHub（比赛要求保留细粒度演进历史）
#
# 用法：
#   powershell -File scripts/daily_push.ps1
#   powershell -File scripts/daily_push.ps1 -Message "feat(locate): 章节匹配"
#
# 第一次用之前，先配好远端和代理（只需一次）：
#   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
#   git config --global http.proxy http://127.0.0.1:7897

param(
    [string]$Message = ""
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$git = 'C:\Program Files\Git\cmd\git.exe'
if (-not (Test-Path $git)) { $git = 'git' }

# 有改动才提交，避免空提交污染历史
$dirty = & $git status --porcelain
if (-not $dirty) {
    Write-Host "没有改动，跳过提交。" -ForegroundColor Yellow
} else {
    if (-not $Message) {
        $stamp = Get-Date -Format 'MM-dd HH:mm'
        $count = ($dirty | Measure-Object).Count
        $Message = "chore: 每日进度 $stamp（$count 个文件，AI 协作）"
    }
    & $git add -A
    & $git commit -q -m $Message
    Write-Host "已提交：$Message" -ForegroundColor Green
}

# 有远端才推
$remote = & $git remote
if (-not $remote) {
    Write-Host "还没有远端。先执行：" -ForegroundColor Yellow
    Write-Host "  git remote add origin https://github.com/<你的用户名>/<仓库名>.git"
    exit 0
}

Write-Host "推送到 $remote ..." -ForegroundColor Cyan
& $git push
if ($LASTEXITCODE -ne 0) {
    Write-Host "推送失败。常见原因：" -ForegroundColor Red
    Write-Host "  1) 没配代理：git config --global http.proxy http://127.0.0.1:7897"
    Write-Host "  2) 没登录：推送时会要求输入用户名 + Personal Access Token（不是密码）"
    exit $LASTEXITCODE
}
Write-Host "完成。今天的历史已上 GitHub。" -ForegroundColor Green
