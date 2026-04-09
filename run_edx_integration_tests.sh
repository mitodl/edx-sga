#!/bin/bash
set -e

source /openedx/venv/bin/activate

cd /openedx/edx-platform
mkdir -p reports

pip install -r requirements/edx/testing.txt

pip install -e .

cd /edx-sga
pip uninstall edx-sga -y
pip install -e .

# output the packages which are installed for logging
pip freeze

# adjust test files for integration tests
# Copy setup.cfg if it exists, otherwise try pyproject.toml
if [ -f /openedx/edx-platform/setup.cfg ]; then
  cp /openedx/edx-platform/setup.cfg .
elif [ -f /openedx/edx-platform/pyproject.toml ]; then
  cp /openedx/edx-platform/pyproject.toml .
else
  echo "Neither setup.cfg nor pyproject.toml found, skipping."
fi
rm ./pytest.ini
mkdir test_root  # for edx

pytest ./edx_sga/tests/integration_tests.py --cov . --ds=lms.envs.test
coverage xml
