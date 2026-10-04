#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
if [[ ! -x build/rings-of-power/rings-of-power ]]; then
    printf '%s\n' 'Executable missing. See docs/usage.md for the build command.' >&2
    exit 1
fi
exec ./build/rings-of-power/rings-of-power --window --audio on "$@"
