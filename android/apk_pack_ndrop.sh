#!/bin/bash

# for p4a
# sudo apt install -y \
#     build-essential \
#     ccache \
#     git \
#     zlib1g-dev \
#     python3 \
#     python3-dev \
#     unzip \
#     ant \
#     openjdk-11-jdk \
#     ccache \
#     autoconf \
#     lld \
#     libtool \
#     libffi-dev \
#     libssl-dev

# libncurses5:i386 \
# libstdc++6:i386 \
# zlib1g:i386 \

# permission:
# https://developer.android.com/reference/android/Manifest.permission
# https://github.com/kivy/python-for-android/blob/master/pythonforandroid/recipes/android/src/android/permissions.py

p4a apk \
    --private $HOME/ndrop \
    --package "org.network.ndrop" \
    --name "NDrop" \
    --icon "$HOME/ndrop/ndrop/image/ndrop.png" \
    --dist-name "ndrop" \
    --version 1.6.11 \
    --sdk-dir "$HOME/ndrop/android/sdk" \
    --ndk-dir "$HOME/ndrop/android/android-ndk-r19c" \
    --ndk-api 21 \
    --android-api 27 \
    --arch arm64-v8a \
    --permission WRITE_EXTERNAL_STORAGE \
    --permission READ_EXTERNAL_STORAGE \
    --permission MANAGE_EXTERNAL_STORAGE \
    --permission INTERNET \
    --permission ACCESS_NETWORK_STATE \
    --permission ACCESS_WIFI_STATE \
    --presplash "$HOME/ndrop/ndrop/image/splash.png" \
    --presplash-color white \
    --window \
    --wakelock \
    --bootstrap=sdl2 \
    --blacklist blacklist.txt \
    --release \
    --ignore-setup-py \
    --requirements=python3,kivy,ifaddr,pillow,tqdm,platformdirs
    # --blacklist-requirements \
