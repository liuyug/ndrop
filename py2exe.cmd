
rmdir build /s /q
del dist\ndrop.exe /q
pyinstaller ndrop.spec

dist\ndrop.exe
