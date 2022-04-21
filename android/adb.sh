#!/bin/bash

# check cpu arch
# getprop ro.product.cpu.abi

SDK_DIR="$HOME/ndrop/android/sdk"

$SDK_DIR/platform-tools/adb $*
