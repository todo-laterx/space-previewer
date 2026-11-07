#!/usr/bin/env bash
# Build a Fedora RPM with the standalone CLI and Dolphin service menu.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$DIR/VERSION")"
if [[ ! "$VERSION" =~ ^[0-9]+(\.[0-9]+)*$ ]]; then
    echo "Unsupported RPM version: $VERSION" >&2
    exit 2
fi

OPTIONS=()
case "${1:-}" in
    --nodeps) OPTIONS+=(--nodeps) ;;
    "") ;;
    *) echo "Usage: bash scripts/build-rpm.sh [--nodeps]" >&2; exit 2 ;;
esac
if (( $# > 1 )); then
    echo "Usage: bash scripts/build-rpm.sh [--nodeps]" >&2
    exit 2
fi

for tool in rpmbuild tar msgfmt; do
    command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done

TOPDIR="$DIR/build/rpm"
mkdir -p "$TOPDIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS,tmp} "$DIR/dist"

# Build from the working tree so local changes are included, but never ship caches.
tar --exclude=__pycache__ --exclude='*.pyc' \
    --transform="s,^,space-previewer-$VERSION/," \
    -czf "$TOPDIR/SOURCES/space-previewer-$VERSION.tar.gz" \
    -C "$DIR" src po data assets/logo-512.png LICENSE TRADEMARK.md README.md docs/DOLPHIN.md docs/INTEGRATIONS.md

rpmbuild -bb "${OPTIONS[@]}" \
    --define "_topdir $TOPDIR" \
    --define "_tmppath $TOPDIR/tmp" \
    --define "app_version $VERSION" \
    "$DIR/packaging/space-previewer.spec"

RPM_NAME="space-previewer-$VERSION-1.noarch.rpm"
cp "$TOPDIR/RPMS/noarch/$RPM_NAME" "$DIR/dist/$RPM_NAME"
(cd "$DIR/dist" && sha256sum "$RPM_NAME" > "$RPM_NAME.sha256")
echo "==> Built: dist/$RPM_NAME"
