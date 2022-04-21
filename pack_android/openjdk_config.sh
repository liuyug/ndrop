#!/bin/bash

(
cd ~/android_sdk/packages
wget http://security.debian.org/debian-security/pool/updates/main/o/openjdk-8/openjdk-8-jdk_8u322-b06-1~deb9u1_amd64.deb
wget http://security.debian.org/debian-security/pool/updates/main/o/openjdk-8/openjdk-8-jdk-headless_8u322-b06-1~deb9u1_amd64.deb
wget http://security.debian.org/debian-security/pool/updates/main/o/openjdk-8/openjdk-8-jre_8u322-b06-1~deb9u1_amd64.deb
wget http://security.debian.org/debian-security/pool/updates/main/o/openjdk-8/openjdk-8-jre-headless_8u322-b06-1~deb9u1_amd64.deb

sudo dpkg -i openjdk-8-*
)

sudo update-alternatives --config java

java -version
