#!/bin/bash
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
TESTS_VENV_DIR="$HERE/venv"
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

xeet_tests_venv_create()
{
	if [[ -n "${VIRTUAL_ENV}" ]]; then
		abort "Virtual environment activated. Deactivate it before creating tests virtual environment"
	fi

	if [[ -d "${TESTS_VENV_DIR}" ]]; then
		echo "Virtual environment already exists at ${TESTS_VENV_DIR}"
		return
	fi
	mkdir -p ${TESTS_VENV_DIR} || abort "Could not create virtual environment directory"
	python3 -m venv ${TESTS_VENV_DIR} || abort "Could not create virtual environment"
	xeet_tests_venv_activate
	pip install --upgrade pip
	deactivate
}

xeet_tests_venv_activate()
{
	if [[ -n "${VIRTUAL_ENV}" ]]; then
		if [[ "${VIRTUAL_ENV}" == "${TESTS_VENV_DIR}" ]]; then
			return
		fi
		abort "None tests-virtual environment already activated"
	fi
	source ${TESTS_VENV_DIR}/bin/activate || abort "Could not activate virtual environment"
}
