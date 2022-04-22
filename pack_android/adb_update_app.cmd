
set apk_file=ndrop-release-signed-1.6.11-aligned.apk
set apk_name=org.network.ndrop

curl -o %apk_file% http://192.168.100.10:8000/%apk_file%

platform-tools\adb uninstall %apk_name%
platform-tools\adb install %apk_file%
