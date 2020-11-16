#!/bin/sh

if [ ! -f tkinterdnd2-master.zip ]; then
    # wget https://github.com/pmgagne/tkinterdnd2/archive/master.zip -O tkinterdnd2-master.zip
    curl -L https://github.com/pmgagne/tkinterdnd2/archive/master.zip -o tkinterdnd2-master.zip
fi

rm -rf tkinterdnd2

unzip tkinterdnd2-master.zip tkinterdnd2-master/tkinterdnd2/*

mv tkinterdnd2-master/tkinterdnd2/ tkinterdnd2/
rmdir tkinterdnd2-master

