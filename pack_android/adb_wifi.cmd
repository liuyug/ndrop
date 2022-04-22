@echo off

echo 当前设备：
platform-tools\adb devices
echo 当前 IP 地址
platform-tools\adb shell "ip a | grep 'inet 1'"

echo 输入命令：
echo platform-tools\adb tcpip 5555
echo platform-tools\adb connect ip:5555
echo platform-tools\adb devices

echo 如果出现 "ip:5555    offline"字样，则
echo 在手机设置：开发者模式，启用"仅充电模式下允许ADB调试"，启用"USB调试"
echo 然后再次运行查看
echo platform-tools\adb devices
