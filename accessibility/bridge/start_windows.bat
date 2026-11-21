@echo off
setlocal
title Tactics Ogre PPSSPP Speaking Bridge
echo Tactics Ogre speaking prototype: installing local Python dependencies.
py -m pip install --user websocket-client pywin32 "winrt-Windows.Media.Ocr[all]" "winrt-Windows.Graphics.Imaging[all]" "winrt-Windows.Storage[all]"
if errorlevel 1 (
  echo.
  echo Dependency installation failed. See the error above.
  pause
  exit /b 1
)
echo.
echo Launching. Use Ctrl+Alt+Shift+O to read, Ctrl+Alt+Shift+P to repeat, Ctrl+Alt+Shift+Q to quit.
py "%~dp0to_speaking_probe.py" --port 56244
if errorlevel 1 pause
endlocal
