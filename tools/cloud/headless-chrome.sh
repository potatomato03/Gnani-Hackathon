#!/bin/sh
# PDF_BROWSER for Claude Code cloud sessions (Linux container, running as root).
# Uses the pre-installed Playwright chrome-headless-shell: the full Chromium binary
# hangs on --print-to-pdf there. Root needs --no-sandbox. The shell binary is always
# headless, so --headless=new from render.py is dropped.
for a; do shift; [ "$a" = "--headless=new" ] || set -- "$@" "$a"; done
for b in /opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell; do
  [ -x "$b" ] && exec "$b" --no-sandbox "$@"
done
echo "headless-chrome.sh: no chrome-headless-shell under /opt/pw-browsers" >&2
exit 1
