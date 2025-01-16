#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source ${DIR}/common.inc.sh

filter_debug_output()
{
    if [[ ${XEET_DEBUG} == "1" ]]; then
        echo "Running in debug mode, skipping stdout manipulation"
        return 0
    fi
    sed -i "s,duration:.*s)$,duration: XXXs),g" ${TEST_OUTPUT_DIR}/stdout
}

filter_debug_output
generic_stdout_test
