#!/bin/bash

# SDK: Android Studio Command line Only
# https://developer.android.com/studio#downloads

# fix directory, such as
# sdk/cmdline-tools/latest/bin
mkdir sdk
mv cmdline-tools latest
mkdir cmdline-tools
mv latest cmdline-tools
mv cmdline-tools sdk

# NDK:
# The minimal, and recommended, NDK version to use is r19b
# https://github.com/android/ndk/wiki/Unsupported-Downloads
# https://dl.google.com/android/repository/android-ndk-r19c-linux-x86_64.zip
# unzip

SDK_DIR=$HOME/ndrop/android/sdk
NDK_DIR=$HOME/ndrop/android/android-ndk-r19c

(
cd sdk
$SDK_DIR/cmdline-tools/latest/bin/sdkmanager "platforms;android-27"
$SDK_DIR/cmdline-tools/latest/bin/sdkmanager "build-tools;28.0.2"
)

