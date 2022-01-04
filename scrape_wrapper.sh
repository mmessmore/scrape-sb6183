#!/bin/bash

BASE_DIR=$(dirname $(realpath "$0"))

if ! cd "$BASE_DIR"; then
	echo "Could not cd to ${BASE_DIR}" >&2
	exit 1
fi

if ! pipenv --venv >/dev/null 2>&1; then
	if ! pipenv install >/dev/null 2>&1; then
		echo "Failed to establish pipenv" >&2
		exit 1
	fi
fi


pipenv run ./scrape.py
