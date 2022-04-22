#!/bin/bash

# check cpu arch
# getprop ro.product.cpu.abi

SDK_DIR="$HOME/android_sdk/sdk"

if [ "x$1" == x ]; then
    echo 命令提示：
    echo adb --help
    echo adb devices
    echo adb shell
    echo adb usb
    echo adb shell getprop ro.product.cpu.abi
    echo adb shell logcat \| grep 'I python'
else
    $SDK_DIR/platform-tools/adb $*
fi
