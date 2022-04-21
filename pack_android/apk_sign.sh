#!/bin/bash

SDK_DIR="$HOME/android_sdk/sdk"
BUILD_TOOLS="$SDK_DIR/build-tools/28.0.3"

if [ "x" == "x$1" ]; then
    echo "$0 <keygen|sign>"
    exit 0
fi

# generate private key using java tools

if [ "xkeygen" == "x$1" ]; then
    keytool -genkey -v \
        -keystore release-key.keystore \
        -alias app \
        -keyalg RSA \
        -keysize 2048 \
        -validity 10000
    exit 0
fi

if [ "xsign" == "x$1" ]; then
    if [ "x" == "x$1" ]; then
        echo "$0 <keygen|sign> <apk>"
        exit 0
    fi
    APK_BASENAME=`basename $2 .apk`
    OUT_BASENAME=`echo ${APK_BASENAME} | sed -e "s/unsigned/signed/"`
    OUT_APK=${OUT_BASENAME}aligned.apk

    rm -f ${OUT_APK}
    # cp    $APK_BASENAME.apk  ${OUT_APK}
    $BUILD_TOOLS/zipalign \
        -v \
        -p 4 \
        $APK_BASENAME.apk \
        ${OUT_APK}

    $BUILD_TOOLS/apksigner \
        sign \
        --verbose \
        --ks-key-alias app \
        --ks release-key.keystore \
        --ks-pass pass:abc123 \
        --key-pass pass:abc123 \
        ${OUT_APK}


    $BUILD_TOOLS/apksigner \
        verify \
        --verbose \
        ${OUT_APK}

    exit 0
fi
# old method
# jarsigner -verbose \
#     -sigalg SHA1withRSA \
#     -digestalg SHA1 \
#     -keystore release-key.keystore \
#     $APK_BASENAME.aligend.apk \
#     apk_app



