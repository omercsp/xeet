#!/bin/bash
# get script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
XEET_DIR=${DIR}/..

# check if we are inside a virtual environment and deactivate it
if [[ $VIRTUAL_ENV != "" ]]; then
    echo "deactivate virtual environment"
    deactivate
fi

# check if xeet is installed by pip
if [[ $(pip list | grep xeet) != "" ]]; then
    echo "xeet is installed by pip"
    pip uninstall xeet -y
fi

cd ${XEET_DIR} || exit 1
pip install .
rm -rf ${XEET_DIR}/build ${XEET_DIR}/dist ${XEET_DIR}/xeet.egg-info




