##
# start_gui.sh: quick script to launch the gui inside a python venv
#
# Requirements: the venv must already be setup in ~/.venv, or
# .venv, or ~/python_venv. Please read README.md or docs/QUICK_START.md
# for requirements for the environment.
#
# Technically python3 -m gui_qt.main could be run without a virutal
# environment, but this is discouraged with linux operating systems
# (like Ubuntu) that require python to be configured in a particular
# way to function properly, and disturbing that setup should be avoided.
##
#!/bin/bash

function error_exit
{
    echo $*
    echo ""
    echo "Please setup a virtual environment for python to live in"
    echo "RECOMMENDED: 'python3 -m venv ~/python_venv/fin_plan'"
    exit 1
}

if [ -e ~/python_venv/fin_plan/bin/activate ]; then
    ACTIVATION=~/python_venv/fin_plan/bin/activate
elif [ -e .venv/bin/activate ]; then
    ACTIVATION=.venv/bin/activate
elif [ -e ~/.venv/bin/activate ]; then
    ACTIVATION=~/.venv/bin/activate
else
    error_exit "failed to find python venv activate"
fi

if [ ${ACTIVATION} ]; then
    source ${ACTIVATION}
    if [ $? != 0 ]; then
	error_exit "failed to source python venv activation"
    fi
    python3 -m gui_qt.main
fi
