#!/usr/bin/env bash
# Re-record docs/demo.gif: a real, live séance (real archive, real Gemma on llama-server).
# Needs: asciinema 2.x, agg (https://github.com/asciinema/agg), llama-server on :8080.
# agg caps idle pauses (waiting on archive.org) at 1.5 s; the model's timings printed
# at the end of the séance are the real ones.
set -euo pipefail
site="${1:-geocities.com}"
cd "$(dirname "$0")/.."
asciinema rec --overwrite --cols 96 --rows 42 -c "seance $site --pace 0.008 -o /tmp/demo.html" docs/demo.cast
agg --idle-time-limit 1.5 --font-size 15 --theme monokai --last-frame-duration 6 docs/demo.cast docs/demo.gif
echo "wrote docs/demo.gif"
