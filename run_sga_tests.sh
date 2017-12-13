#!/bin/bash
set -e

source /edx/app/edxapp/venvs/edxapp/bin/activate

cd /edx/app/edxapp/edx-platform
NO_PYTHON_UNINSTALL=1 paver install_prereqs

cd /edx-sga
pip uninstall edx-sga -y
pip install -e . -r test_requirements.txt

cd /edx/app/edxapp/edx-platform
mkdir -p reports

pytest lms/djangoapps/edx_sga/tests/integration_tests.py
