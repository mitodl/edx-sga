#!/bin/bash
set -e

source /edx/app/edxapp/venvs/edxapp/bin/activate

cd /edx-sga

pip uninstall edx-sga -y
pip install -e .

cd /edx/app/edxapp/edx-platform


# the migrations in the test take more than 10 minutes to set up, so we need to keep travis occupied
(while true; do echo "."; sleep 60; done) &

./manage.py lms --settings=test_docker test edx_sga.tests.integration_tests
