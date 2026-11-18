#!/usr/bin/env bash
# Descarga el dataset ResPlan (CC BY 4.0) en datos/ResPlan/
set -e
mkdir -p datos
if [ ! -d datos/ResPlan ]; then
  git clone --depth 1 https://github.com/m-agour/ResPlan datos/ResPlan
fi
cd datos/ResPlan
[ -f ResPlan.pkl ] || unzip -o ResPlan.zip
echo "Listo: datos/ResPlan/ResPlan.pkl"
