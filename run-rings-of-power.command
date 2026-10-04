#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"
exec ./run-rings-of-power.sh --save-dir "$PWD/saves" --widescreen --zoom --smooth-camera --mouse "$@"
