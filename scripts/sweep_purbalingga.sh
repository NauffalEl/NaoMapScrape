#!/usr/bin/env bash
# Full Purbalingga coffee/cafe sweep.
#
# Runs one process per location so a single keyword hitting a Maps quota
# cannot kill the whole sweep, and each location's CSV stands on its own.
# Keyword x location would otherwise be 36 jobs inside one process, where the
# first failed job only logs and the run continues but a browser crash ends it.
set -u

KW="kopi, kedai kopi, cafe, coffee, roastery, espresso"
LOCS="Purbalingga, Purbalingga Selatan, Kalikabang, Banjaroya, Bojanegara, Padamara"
OUT="data/exports/sweep"
LOG="data/logs/sweep.log"

mkdir -p "$OUT" data/logs
: > "$LOG"

n=0
for loc in ${LOCS//,/ }; do
  slug=$(echo "$loc" | tr ' A-Z' '-a-z')
  n=$((n+1))
  echo "=== [$n/6] $loc ===" | tee -a "$LOG"
  python main.py "$KW" \
    --locations "$loc" \
    --limit 120 \
    --export "$OUT/${slug}.csv" >> "$LOG" 2>&1
  echo "--- $loc exit=$? rows=$(wc -l < "$OUT/${slug}.csv" 2>/dev/null || echo 0)" \
    | tee -a "$LOG"
done

echo "SWEEP DONE" | tee -a "$LOG"