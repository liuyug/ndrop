
call ..\env_noqt\Scripts\activate

rmdir build /s /q
rmdir dist\ndrop /s /q
mkdir build

set script=build\ndrop-script.py
set scriptk=build\ndrop-tk-script.py

echo import ndrop.__main__ >> %script%
echo ndrop.__main__.run() >> %script%

pyinstaller ^
--name ndrop ^
--icon ndrop\image\ndrop.ico ^
--noconfirm ^
%script%


echo import ndrop.__main_tk__ >> %scriptk%
echo ndrop.__main_tk__.run() >> %scriptk%

pyinstaller ^
--name ndroptk ^
--icon ndrop\image\ndrop.ico ^
--hidden-import tkinterdnd2 ^
--add-data tkinterdnd2\tkdnd\win64;tkinterdnd2\tkdnd\win64 ^
--add-data ndrop\image;ndrop\image ^
--windowed ^
--noconfirm ^
%scriptk%

del *.spec

xcopy dist\ndroptk\* dist\ndrop /s /y
rmdir dist\ndroptk /s /q

call ..\env_noqt\Scripts\deactivate
