#!/data/data/com.termux/files/usr/bin/bash
# update_epg.sh  – Termux cron driver

set -e
cd eagle

# ---------- 1) sync with remote (handles concurrent pushes) ----------
git pull --rebase --autostash origin main   # change branch name if not 'main'

# ---------- 2) build the EPG ----------
python ../script2_termux.py

# ---------- 3) commit & push if file2.xml changed ----------
if git diff --quiet file2.xml; then
    echo "No changes – $(date)"
else
    git add file2.xml
    git commit -m "EPG update $(date '+%Y-%m-%d %H:%M:%S')"
    git push        # will succeed because we just rebased
fi
