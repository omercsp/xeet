#!/bin/bash
PROJ_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)

if [ -z "${PROJ_ROOT}" ]; then
	echo "ERROR: Could not find project root. Are you in the project directory?"
	exit 1
fi

abort()
{
    echo "Error: $1"
    exit 1
}

if [ -z ${USE_SYSTEM_XEET} ]; then
	USE_SYSTEM_XEET=0
fi

if [[ ${USE_SYSTEM_XEET} == "1" ]]; then
	if [[ -n ${VIRTUAL_ENV} ]]; then
		abort "Cannot use system xeet while in a virtual environment"
	fi
	if ! command -v xeet &> /dev/null; then
		abort "Cannot find system xeet"
	fi
elif [[ -z ${VIRTUAL_ENV} ]]; then
	if [[ -z ${XEET_PKG_VENV_PATH} ]]; then
		venv_path=${PROJ_ROOT}/.venv
	else
		venv_path=${XEET_PKG_VENV_PATH} # This set by the package test script
	fi
	source ${venv_path}/bin/activate || abort "Could not activate virtual environment"
fi

xeet --no-colors --no-splash "$@"
