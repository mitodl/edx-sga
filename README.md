Staff Graded Assignment XBlock
==============================

This package provides an XBlock for use with the edX platform which provides a staff graded assignment. Students are invited to upload files which encapsulate their work on the assignment. Instructors are then able to download the files and enter grades for the assignment.

Note that this package is both an XBlock and a Django application. For installation:

1. [edX Developer Stack Installation](https://github.com/edx/configuration/wiki/edX-Developer-Stack): Install Vagrant, Pip, & VirtualBox
    1. Install Virtual Box (Version 4.3.12).
    2. Install Pip `sudo easy_install pip`
    3. Install Vagrant (Version 1.6.3).
    4. Install Vagrant plugin.
        1. Download the Vagrantfile.
        2. Get the virtual machine running.
    ```sh
    mkdir devstack
    cd devstack
    curl –L https://raw.githubusercontent.com/edx/configuration/master/vagrant/release/devstack/Vagrantfile > Vagrantfile
    vagrant plugin install vagrant-vbguest
    vagrant up
    vagrant ssh
    ```

2. Install Package using Pip install (with VM running)
    - `pip install -e git+https://github.com/mitodl/edx-sga@master#egg=edx-sga`
3. Add edx_sga to INSTALLED_APPS in Django settings. Enable an XBlock for testing in your devstack.
    - In `edx-platform/lms/envs/common.py`, uncomment:
    ```sh
    # from xmodule.x_module import prefer_xmodules  
    # XBLOCK_SELECT_FUNCTION = prefer_xmodules  
    ```
    - In `edx-platform/cms/envs/common.py`, uncomment:  
    ```sh
    # from xmodule.x_module import prefer_xmodules  
    # XBLOCK_SELECT_FUNCTION = prefer_xmodules  
    ```
    - In `edx-platform/cms/envs/common.py`, change: 
    ```sh
    ‘ALLOW_ALL_ADVANCED_COMPONENTS’: False,
    ```
    to
    ```sh
    ‘ALLOW_ALL_ADVANCED_COMPONENTS’: True,
    ```
4. Log in to studio (with VM running).
    1. Login
    ```sh
    sudo su edxapp
    paver devstack studio
    ```
    2. Open a browser and navigate to the following link. [http://localhost:8001/](http://localhost:8001/)
    3. Login through the user interface using one of the following accounts.
        - `staff@example.com / edx`
        - `verified@example.com / edx`
        - `audit@example.com / edx`
        - `honor@example.com / edx`

5. Change Advanced Settings
    1. Open a course you are authoring and select "Settings" ⇒ "Advanced Settings
    2. Navigate to the section titled “Advanced Modules”
    3. Add “edx_sga” to module list.
    4. Now when you add an “Advanced” unit in Studio, “Staff Graded Assignment” will be an option.

![image](/../screenshots/img/screenshot-studio-new-unit.png?raw=tru)
