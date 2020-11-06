@echo off

set MAKENSIS="c:\Program Files (x86)\NSIS\Bin\makensis.exe"

echo on
%MAKENSIS% /V4 inst_script.nsi
