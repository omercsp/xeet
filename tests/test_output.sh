#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd ${SCRIPT_DIR} || abort "Failed to cd to ${SCRIPT_DIR}"

SCRIPT_REAL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
source ${SCRIPT_REAL_DIR}/devel_common.inc.sh

test_name=$1
SHOW_TOOL=${SHOW_TOOL:-vim}

if [ -z "$test_name" ]; then
	echo "Usage: $0 <test_name>"
	exit 1
fi

out_dir=$(_get_test_dir ${OUT_BASE_DIR} ${test_name}) || abort ${out_dir}
cmd="${SHOW_TOOL} ${out_dir}/stp0/stdout.filtered"
std_err=${out_dir}/stp0/stderr_filtered
if [ -f ${std_err} ]; then
	cmd="${cmd} ${std_err}"
fi

${cmd}

