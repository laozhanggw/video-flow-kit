@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ============================================================
echo  设置本机路径
echo ============================================================
echo.
where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0设置本机路径.py"
    goto end
)
where py >nul 2>nul
if %errorlevel%==0 (
    py "%~dp0设置本机路径.py"
    goto end
)
echo 没找到 Python。
echo.
echo 两个办法，任选一个：
echo   1. 装一个 Python（python.org，安装时勾选 Add to PATH），再双击本文件
echo   2. 打开 01_给AI的接手指南.md，把里面的第一步交给 AI 做
echo.
:end
echo.
pause
