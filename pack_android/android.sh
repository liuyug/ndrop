#!/bin/bash

# SDK: Android Studio Command line Only
# https://developer.android.com/studio#downloads

# fix directory, such as
# sdk/cmdline-tools/latest/bin

mkdir -p ~/android_sdk/sdk
(
cd ~/android_sdk/sdk
mv cmdline-tools latest
mkdir cmdline-tools
mv latest cmdline-tools
mv cmdline-tools sdk
)
# NDK:
# The minimal, and recommended, NDK version to use is r19b
# https://github.com/android/ndk/wiki/Unsupported-Downloads
# https://dl.google.com/android/repository/android-ndk-r19c-linux-x86_64.zip
# unzip

SDK_DIR=$HOME/android_sdk/sdk
NDK_DIR=$HOME/android_sdk/android-ndk-r19c

(
cd $SDK_DIR
$SDK_DIR/cmdline-tools/latest/bin/sdkmanager "platforms;android-27"
$SDK_DIR/cmdline-tools/latest/bin/sdkmanager "build-tools;28.0.2"
)

