#!/usr/bin/env bash


function __f__ {
    local __root
    __root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ ! -d "${__root}/env" ]] ;
    then
        python3 -m venv "${__root}/env" || { printf "ERROR: python3 venv\n" ; exit 1 ; }
    fi
    source "${__root}/env/bin/activate" || { printf "ERROR: python3 activate\n" ; exit 1 ; }
    python3 -m pip install --upgrade pip || { printf "ERROR: python3 upgrade pip\n" ; exit 1 ; }
    python3 -m pip install -r "${__root}/requirements.txt" || { printf "ERROR: python3 upgrade\n" ; exit 1 ; }
    python3 main.py || { printf "ERROR: python3 venv\n" ; exit 1 ; }
    if [[ "function" == "$(type -t deactivate)" ]] ;
    then
        deactivate
    fi
    true
}

__f__
unset __f__

