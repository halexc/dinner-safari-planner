#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo 'Please run install.command first. See "INSTALL (For Dummies).md".'
    read -r -p "Press Return to close... "
    exit 1
fi
.venv/bin/python -m cykelfest_routing "$@"
result=$?
if [ "$result" -ne 0 ]; then
    echo "Cykelfest could not start. Read the error above, or run install.command again."
    read -r -p "Press Return to close... "
fi
exit "$result"
