@echo off
setlocal
title Tactics Ogre PPSSPP Speaking Bridge
echo Tactics Ogre speaking prototype: installing local Python dependencies.
py -m pip install --user websocket-client pywin32 "winrt-Windows.Media.Ocr[all]"
if errorlevel 1 (
  echo.
  echo Dependency installation failed. See the error above.
  pause
  exit /b 1
)
echo.
echo Launching. In PPSSPP press F8 to read, F9 to repeat, F10 to quit.
py "%~dp0to_speaking_probe.py" --port 56244
if errorlevel 1 pause
endlocal
