#!/usr/bin/env bash
# All package builders use the same manifest, regardless of build order.
set -euo pipefail
cd "$1"
shopt -s nullglob
packages=(*.deb *.rpm *.AppImage)
if ((${#packages[@]})); then
    sha256sum -- "${packages[@]}" > SHA256SUMS
else
    : > SHA256SUMS
fi
