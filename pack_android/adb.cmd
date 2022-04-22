@echo off

if x%1 == x (
    echo √¸¡ÓÃ· æ£∫
    echo adb --help
    echo adb devices
    echo adb shell
    echo adb usb
    echo adb shell getprop ro.product.cpu.abi
    echo adb shell logcat ^| grep 'I python'
) else (
    platform-tools\adb %1 %2 %3 %4 %5 %6 %7 %8 %9
)
