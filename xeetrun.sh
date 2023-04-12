#!/bin/bash
_venv_activate()
{
	[[ -n ${VENV_ACTIVATE} ]] && return

	# Stupid Apple
	if [[ ${OSTYPE} == 'darwin'* ]]; then
		READLINK="greadlink"
	else
		READLINK="readlink"
	fi

	SCRIPT_FILE="$(${READLINK} -f ${BASH_SOURCE[0]})"
	SCRIPT_DIR="$(dirname $SCRIPT_FILE)"
	for e in .venv venv env .env; do
		activate_file=${SCRIPT_DIR}/${e}/bin/activate
		if [[ -f ${activate_file} ]]; then
			source ${activate_file}
			break
		fi
	done
}

_venv_activate
xeet "$@"
