@echo off
rem Same as Start-API.bat, plus a public ngrok link anyone can open.
rem The link works only while this window (and this laptop) stays on.
call "%~dp0Start-API.bat" --public %*
