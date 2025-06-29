#!/data/data/com.termux/files/usr/bin/bash
set -e
cd "$(dirname "$0")"

python script2_termux.py

if git diff --quiet file2.xml; then
    echo "No changes – $(date)"
else
    git add file2.xml
    git commit -m "Update EPG $(date '+%Y-%m-%d %H:%M:%S')"
    git push
fi
