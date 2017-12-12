#!/bin/bash
set -e

source /edx/app/edxapp/venvs/edxapp/bin/activate

cd /edx-sga

pip uninstall edx-sga -y
pip install -e . -r test_requirements.txt

cd /edx/app/edxapp/edx-platform
mkdir reports

pytest /edx-sga/edx_sga/tests/integration_tests.py
