
rmdir build /s /q
del dist\ndrop.exe /q

mkdir build

set script=build\ndrop-script.py

echo import ndrop.__main__ >> %script%
echo ndrop.__main__.run() >> %script%

pyinstaller ^
--onefile ^
--name ndrop ^
--exclude-module tkinter ^
--noconfirm ^
%script%

rem dist\ndrop.exe
