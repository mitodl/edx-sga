"""Setup for edx-sga XBlock."""
import os

from setuptools import find_packages, setup

import edx_sga


def package_data(pkg, root_list):
    """Generic function to find package_data for `pkg` under `root`."""
    data = []
    for root in root_list:
        for dirname, _, files in os.walk(os.path.join(pkg, root)):
            for fname in files:
                data.append(os.path.relpath(os.path.join(dirname, fname), pkg))

    return {pkg: data}


setup(
    name="edx-sga",
    version=edx_sga.__version__,
    description="edx-sga Staff Graded Assignment XBlock",
    license="GNU Affero General Public License v3 or later (AGPLv3+)",
    url="https://github.com/mitodl/edx-sga",
    author="MITx",
    zip_safe=False,
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
        "Operating System :: OS Independent",
        "Natural Language :: English",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 2.2",
        "Framework :: Django :: 3.0",
        "Framework :: Django :: 3.1",
        "Framework :: Django :: 3.2",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Education",
    ],
    install_requires=[
        "XBlock",
        "xblock-utils",
        "web_fragments",
    ],
    entry_points={
        "xblock.v1": [
            "edx_sga = edx_sga.sga:StaffGradedAssignmentXBlock",
        ]
    },
    package_data=package_data("edx_sga", ["static", "templates"]),
)
