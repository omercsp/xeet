#!/bin/bash
# Don't follow symlinks, as it is used from different directories as symlink
HERE=$(dirname "$(realpath -s "${BASH_SOURCE[0]}")")

TEST_NAME=$1
expected_dir=${HERE}/xeet.expected
expected_stdout=${expected_dir}/${TEST_NAME}/stdout
expected_stderr=${expected_dir}/${TEST_NAME}/stderr

ret=0
if [[ -e ${expected_stdout} ]]; then
    ! diff ${expected_stdout} ${TEST_OUTPUT_DIR}/stdout && ret=1
fi

if [[ -e ${expected_stderr} ]]; then
    ! diff ${expected_stderr} ${TEST_OUTPUT_DIR}/stderr && ret=1
fi

exit $ret
