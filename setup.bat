@echo off
if not exist .venv goto :create_venv
set /p REBUILD=Virtual environment already exists. Recreate it? [y/N]:
if /i "%REBUILD%"=="y" goto :recreate
goto :install

:recreate
echo Removing old .venv...
rmdir /s /q .venv

:create_venv
echo [1/4] Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo.
    echo ERROR: Could not create venv. Make sure Python 3.11+ is installed and in PATH.
    pause
    exit /b 1
)

:install
echo [2/4] Upgrading pip...
.venv\Scripts\python -m pip install --upgrade pip -q

echo [3/4] Installing dependencies...
.venv\Scripts\pip install . -q
if errorlevel 1 (
    echo.
    echo ERROR: Dependency installation failed.
    pause
    exit /b 1
)
if exist crypto_asset_tracker.egg-info rmdir /s /q crypto_asset_tracker.egg-info
if exist build rmdir /s /q build

echo [4/4] Installing Playwright browser (Chromium)...
.venv\Scripts\playwright install chromium
if errorlevel 1 (
    echo.
    echo ERROR: Playwright browser install failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo Next steps:
echo   1. Copy .env.example to .env and fill in API keys
echo   2. Run query:  .venv\Scripts\python main.py
echo   3. Start bot:  .venv\Scripts\python -m src.telegram_bot.bot
echo.
echo Usage:
echo   python main.py              show all balances
echo   python main.py --image      also export PNG + HTML to output/
echo   python main.py --wallet 0xABC...        query EVM address
echo   python main.py --wallet 0xABC... --chain ethereum
echo   python main.py --help       list available chains

pause
