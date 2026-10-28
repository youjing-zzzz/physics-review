@echo off
rem 双击/命令行都能用：绕过 PowerShell 执行策略限制
rem 用法：ocr.bat "某张图.jpg"  或  ocr.bat "某个目录"
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ocr_windows.ps1" %*
pause
