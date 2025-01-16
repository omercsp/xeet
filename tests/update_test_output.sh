#!/bin/bash
set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd ${SCRIPT_DIR} || abort "Failed to cd to ${SCRIPT_DIR}"

SCRIPT_REAL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
source ${SCRIPT_REAL_DIR}/devel_common.inc.sh

test_name=$1

if [ -z "$test_name" ]; then
	echo "Usage: $0 <test_name>"
	exit 1
fi

test_out_dir=$(_get_test_dir ${OUT_BASE_DIR} ${test_name}) ||  \
	abort "Error getting test directory for ${test_name}"
test_out_dir=${test_out_dir:?}/stp0
expected_dir=$(_get_test_dir ${EXPECTED_BASE_DIR} ${test_name}) || \
	abort "Error getting expected directory for ${test_name}"
expected_dir=${expected_dir:?}/stp0

if [[ -d ${expected_dir} ]]; then
	rm -rf ${expected_dir:?}
fi

mkdir -p ${expected_dir:?}

for f in stdout stderr; do
	out_file=${test_out_dir}/${f}.filtered
	[[ ! -f ${out_file} ]] && continue
	cp -v ${out_file} ${expected_dir}
done
