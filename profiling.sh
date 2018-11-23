#!/bin/bash
if [ $1 -eq 1 ]
then
echo enable.
find ./blacksheep/*.pxd -maxdepth 1 -type f -exec sed -i ' 1 s/.*/&, profile=True/' {} \;
find ./blacksheep/*.pyx -maxdepth 1 -type f -exec sed -i '1s;^;# cython: profile=True\n;' {} \;
else
echo disable
find ./blacksheep/*.pyx -maxdepth 1 -type f -exec sed -i '/# cython: profile=True/d' {} \;
find ./blacksheep/*.pxd -maxdepth 1 -type f -exec sed -i 's/, profile=True//g' {} \;
fi