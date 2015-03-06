# This script will test SGA, do code quality test and coverage
# sudo su edxapp
# Run: ../venvs/edxapp/src/edx-sga/edx_sga/script/run_quality.sh
#
echo "Pylint analysis:"
pylint /edx/app/edxapp/venvs/edxapp/src/edx-sga/edx_sga/* --errors-only

echo "Pep8 analysis:"
pep8 /edx/app/edxapp/venvs/edxapp/src/edx-sga/edx_sga/*

echo "\n Code coverage: \n"
coverage run --source edx_sga manage.py lms --settings=test test edx_sga
coverage report -m
