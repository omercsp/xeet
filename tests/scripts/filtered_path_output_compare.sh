#!/bin/bash
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source ${DIR}/common.inc.sh

generic_xeet_path_filter
generic_stdout_test
