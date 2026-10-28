# 一键准备并启动（Windows PowerShell）
#
# 目标：任何人 clone 下来，10 分钟内能跑起来。
# 原则：不写死绝对路径、不改系统环境、失败时给下一步提示。

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "== 1/4 检查 Python ==" -ForegroundColor Cyan
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "没找到 python。请先装 Python 3.11+ 并勾选 Add to PATH。" -ForegroundColor Red
    Write-Host "下载：https://www.python.org/downloads/"
    exit 1
}
$ver = & python --version
Write-Host "  $ver"

Write-Host "== 2/4 安装依赖 ==" -ForegroundColor Cyan
& python -m pip install --disable-pip-version-check -q -r backend/requirements.txt
& python -m pip install --disable-pip-version-check -q pypdf
Write-Host "  依赖就绪"

Write-Host "== 3/4 初始化数据库 ==" -ForegroundColor Cyan
& python scripts/check_db.py

Write-Host "== 4/4 启动服务 ==" -ForegroundColor Cyan
Write-Host "  打开 http://127.0.0.1:8000/health 应返回 status=ok"
Write-Host "  Ctrl+C 停止`n"
& python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
