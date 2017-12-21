#!/bin/bash
set -e

source /edx/app/edxapp/venvs/edxapp/bin/activate

cd /edx/app/edxapp/edx-platform
mkdir -p reports

# these pip install commands are adapted from edx-platform/circle.yml
pip install --exists-action w -r requirements/edx/paver.txt

# Mirror what paver install_prereqs does.
# After a successful build, CircleCI will
# cache the virtualenv at that state, so that
# the next build will not need to install them
# from scratch again.
pip install --exists-action w -r requirements/edx/pre.txt
pip install --exists-action w -r requirements/edx/github.txt
pip install --exists-action w -r requirements/edx/local.txt

# HACK: within base.txt stevedore had a
# dependency on a version range of pbr.
# Install a version which falls within that range.
pip install  --exists-action w pbr==0.9.0
pip install --exists-action w -r requirements/edx/django.txt
pip install --exists-action w -r requirements/edx/base.txt
pip install --exists-action w -r requirements/edx/paver.txt
pip install --exists-action w -r requirements/edx/testing.txt
if [ -e requirements/edx/post.txt ]; then pip install --exists-action w -r requirements/edx/post.txt ; fi

cd /edx-sga
pip uninstall edx-sga -y
pip install -e .

# Install codecov so we can upload code coverage results
pip install codecov

# output the packages which are installed for logging
pip freeze

# adjust test files for integration tests
cp /edx/app/edxapp/edx-platform/setup.cfg .
rm ./pytest.ini
mkdir test_root  # for edx

pytest ./edx_sga/tests/integration_tests.py --cov .
coverage xml
codecov
