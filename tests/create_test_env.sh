#!/bin/bash
set -e
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
source ${HERE}/test_env.inc.sh

xeet_tests_venv_create
xeet_tests_venv_activate
pip install -e ${PROJ_ROOT} || _abort "Could not install project in virtual environment"
