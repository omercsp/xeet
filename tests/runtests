#!/bin/bash
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd ${HERE} || exit 1

# xeet_tests_venv_activate
XEET_BIN=$(which xeet 2>/dev/null)

set -e
if [[ -z ${XEET_BIN} ]]; then
	echo "xeet is not installed in search path."
	exit 1
fi

if [[ -n "${VIRTUAL_ENV}" ]]; then
	echo "This is a high level xeet test script"
	echo "Since we use xeet to test itself, the xeet used here shouldn't be from a virtual environment,"
	echo "but from the system path where a stable version of xeet is installed."
	echo "Please deactivate the virtual environment and make installed xeet in the system path before running this script."
	echo ""
	exit 1
fi


echo "Using xeet from '${XEET_BIN}'"
if [[ -n ${XEET_PKG_VENV_PATH} ]]; then
	echo "Internal XEET virtual environment path is set to ${XEET_PKG_VENV_PATH}"
fi
${XEET_BIN} run -c ${HERE}/xeet.json "$@"
