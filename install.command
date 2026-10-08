#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
echo "Installing Cykelfest. Please keep this window open."
if command -v python3.13 >/dev/null 2>&1; then
    python3.13 scripts/install.py
elif [ -x /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 ]; then
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 scripts/install.py
elif python3 -c 'import sys; sys.exit(sys.version_info[:2] != (3, 13))' >/dev/null 2>&1; then
    python3 scripts/install.py
else
    echo 'Python 3.13 was not found. See "INSTALL (For Dummies).md".'
    read -r -p "Press Return to close... "
    exit 1
fi
result=$?
if [ "$result" -ne 0 ]; then
    echo "Installation failed. Read the error above for the next step."
fi
read -r -p "Press Return to close... "
exit "$result"
