@echo off

for /F %%i in ('python -c "from ndrop import about; print(about.version)"') do ( set version=%%i)

echo %version%

set MAKENSIS="c:\Program Files (x86)\NSIS\Bin\makensis.exe"

echo on
%MAKENSIS% /V4 /DPRODUCT_VER=%version% inst_script.nsi
