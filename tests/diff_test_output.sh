#!/bin/bash
set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd ${SCRIPT_DIR} || abort "Failed to cd to ${SCRIPT_DIR}"

SCRIPT_REAL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
source ${SCRIPT_REAL_DIR}/devel_common.inc.sh
# '--not-a-term' is to supress the 'files to edit' message
DIFF_TOOL=${DIFF_TOOL:-vimdiff --not-a-term}

test_name=$1

if [ -z "$test_name" ]; then
	echo "Usage: $0 <test_name>"
	exit 1
fi

test_expected_dir=$(_get_test_dir ${EXPECTED_BASE_DIR} ${test_name}) || abort ${test_expected_dir}
test_out_dir=$(_get_test_dir ${OUT_BASE_DIR} ${test_name}) || abort ${test_out_dir}
test_out_dir=${test_out_dir:?}/stp0

_diff_file()
{
	local src_file=${test_expected_dir}/$1
	local dst_file=${test_out_dir}/$1.filtered

	if [[ ! -f ${src_file} && ! -f ${dst_file} ]]; then
		echo "Files ${src_file} and ${dst_file} do not exist, nothing to compare"
		return 0
	fi

	if [[ ! -f ${src_file} ]]; then
		warn "'${dst_file}' found, but '${src_file}' does not exist"
		return 1
	fi

	if [[ ! -f ${dst_file} ]]; then
		warn "'${src_file}'' found but, '${dst_file}'' does not exist"
		return 1
	fi

	if cmp -s ${src_file} ${dst_file}; then
		echo "Files ${src_file} and ${dst_file} are identical"
		return 0
	fi

	echo "Files ${src_file} and ${dst_file} differ"
	${DIFF_TOOL} ${src_file} ${dst_file}
}

_diff_file stdout
_diff_file stderr
