#!/bin/zsh
# Spike (g): detect running claude processes and their cwd. Read-only.
set -u
echo "== pgrep -lx claude"; time pgrep -lx claude
echo "== pgrep -fl claude (first 60 chars)"; time pgrep -fl claude | cut -c1-60
pids=$(pgrep -x claude | paste -sd, -)
echo "== lsof cwd for -x pids [$pids]"
[ -n "$pids" ] && { time lsof -a -d cwd -p "$pids" -Fn; }
