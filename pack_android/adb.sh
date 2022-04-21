#!/bin/bash

# check cpu arch
# getprop ro.product.cpu.abi

SDK_DIR="$HOME/android_sdk/sdk"

$SDK_DIR/platform-tools/adb $*
