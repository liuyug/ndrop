
rmdir build /s /q
rmdir dist\ndrop /s /q
pyinstaller ndrop.spec

dist\ndrop.exe
