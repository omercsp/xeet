#!/bin/bash
set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd ${SCRIPT_DIR} || abort "Failed to cd to ${SCRIPT_DIR}"

SCRIPT_REAL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
source ${SCRIPT_REAL_DIR}/devel_common.inc.sh

test_name=$1
force=${FORCE:-0}

if [ -z "$test_name" ]; then
	echo "Usage: $0 <test_name>"
	exit 1
fi

test_out_dir=$(_get_test_dir ${OUT_BASE_DIR} ${test_name}) ||  \
	abort "Error getting test directory for ${test_name}"
test_name=$(basename ${test_out_dir:?})
test_out_dir=${test_out_dir:?}/stp0
expected_dir=${EXPECTED_BASE_DIR}/${test_name}

if [[ -d ${expected_dir:?} ]]; then
	if [[ ${force} -eq 0 ]]; then
		echo "Expected directory ${expected_dir} already exists. Use FORCE=1 to overwrite."
		exit 1
	fi
	rm -rf ${expected_dir:?}
fi

mkdir -p ${expected_dir:?}

for f in stdout stderr; do
	[[ ! -f ${test_out_dir}/${f} ]] && continue
	cp -v ${test_out_dir}/${f} ${expected_dir}/${f}
done
