@echo off
rem 双击即可：提交并推送到 GitHub（绕过 PowerShell 执行策略限制）
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0daily_push.ps1" %*
pause
