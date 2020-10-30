
rmdir build /s /q
del dist\ndrop.exe /q

mkdir build

set script=build\ndrop-script.py
set scriptk=build\ndrop-tk-script.py

echo import ndrop.__main__ >> %script%
echo ndrop.__main__.run() >> %script%

pyinstaller ^
--onefile ^
--name ndrop ^
--exclude-module tkinter ^
--noconfirm ^
%script%


echo import ndrop.__main_tk__ >> %scriptk%
echo ndrop.__main_tk__.run() >> %scriptk%

pyinstaller ^
--onefile ^
--name ndroptk ^
--hidden-import tkinterdnd2 ^
--add-data tkinterdnd2\tkdnd\win64;tkinterdnd2\tkdnd\win64 ^
--add-data ndrop\image;ndrop\image ^
--noconfirm ^
%scriptk%


rem dist\ndrop.exe
