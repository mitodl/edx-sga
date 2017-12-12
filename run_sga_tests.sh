#!/bin/bash
set -e

source /edx/app/edxapp/venvs/edxapp/bin/activate

cd /edx-sga

pip uninstall edx-sga -y
pip install -e .

cd /edx/app/edxapp/edx-platform

./manage.py lms --settings=test test edx_sga.tests.integration_tests
