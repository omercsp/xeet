#!/bin/bash
set -e

echoerr()
{
    echo "$@" 1>&2;
}

require_var()
{
    local var_name=$1
    #make sure the variable is set
    if [[ -z ${!var_name} ]]; then
        echoerr "Missing variable ${var_name}"
        exit 1
    fi
}

require_dir()
{
    local dir_name=$1
    #make sure the variable is set
    if [[ ! -d ${dir_name} ]]; then
        echoerr "Missing directory ${dir_name}"
        exit 1
    fi
}

require_dir_var()
{
    local dir_var_name=$1
    require_var ${dir_var_name}
    require_dir ${!dir_var_name}
}

require_file()
{
    local file_name=$1
    local file_name_pr=${file_name#"${XEET_ROOT}/"}

    if [[ ! -f ${file_name} ]]; then
        echoerr "Missing file: ${file_name_pr}"
        exit 1
    fi
}

require_not_file()
{
    local file_name=$1

    if [[ -f ${file_name} ]]; then
        echoerr "File ${file_name} should not exist"
        exit 1
    fi
}

_compare_file()
{
    local expected_file=$1
    local out_file=$2
    local expected_file_pr=${expected_file#"${XEET_ROOT}/"}
    local out_file_pr=${out_file#"${XEET_ROOT}/"}

    if [[ -f ${expected_file} ]]; then
        require_file ${out_file}
    else
        if [[ ! -f ${out_file} ]]; then
            return 0
        fi
    fi

    if [[ -f ${out_file} ]]; then
        require_file ${expected_file}
    else
        require_not_file ${expected_file}
    fi

    sed -i "s,${XEET_ROOT},__XEET_ROOT__,g" ${out_file}
    sed -i -E 's/[0-9]+\.[0-9]{3}s/X.XXXs/g' ${out_file}

    if diff -q ${out_file} ${expected_file} &> /dev/null; then
        echo "File ${out_file_pr} matches expected output"
    else
        echoerr "Files ${out_file_pr} and ${expected_file_pr} do not match"
	echoerr "Diff saved to ${out_file_pr}.diff"
        diff -u ${out_file} ${expected_file} &> ${out_file}.diff
        return 1
    fi
}

require_var TEST_NAME
require_var XEET_DEBUG

require_dir_var TEST_OUTPUT_DIR
require_dir_var XEET_ROOT

TEST_EXPECTED_DIR=${XEET_ROOT}/xeet.expected/${TEST_NAME}

if [[ ${XEET_DEBUG} == "1" ]]; then
	echo "Running in debug mode, skipping stdout comparison"
	return 0
fi

_compare_file ${TEST_EXPECTED_DIR}/stdout ${TEST_OUTPUT_DIR}/stdout
_compare_file ${TEST_EXPECTED_DIR}/stderr ${TEST_OUTPUT_DIR}/stderr
