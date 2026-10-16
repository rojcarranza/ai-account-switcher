#!/bin/sh
# G-1(h)/(i) spike: a throwaway SwiftBar plugin. Copy into the SwiftBar plugin
# folder as ais-probe.1m.sh, look at the menu once, then delete it.
# Logs what SwiftBar gives plugins to spike/raw/swiftbar.log (git-ignored).
LOG="/Users/roj/Dev/projects/ai-account-switcher/.claude/worktrees/ais-mvp/spike/raw/swiftbar.log"
{
  echo "== $(date -u +%Y%m%dT%H%M%SZ)"
  echo "PATH=$PATH"
  echo "tty: $(tty 2>&1)"
  echo "claude on PATH: $(command -v claude || echo none)"
  start=$(python3 -c 'import time; print(time.time())' 2>/dev/null)
  out=$("$HOME/.local/bin/claude" auth status >/dev/null 2>&1 </dev/null; echo $?)
  end=$(python3 -c 'import time; print(time.time())' 2>/dev/null)
  echo "claude auth status exit=$out start=$start end=$end"
} >> "$LOG" 2>&1
echo "ais probe"
echo "---"
echo "PATH: $PATH | size=11"
echo "Disabled item test | disabled=true"
echo "Action test (writes a line to the log) | bash=/bin/sh param1=-c param2=\"echo action-ran >> '$LOG'\" terminal=false"
echo "Terminal action test | bash=/bin/echo param1=terminal-ok terminal=true"
