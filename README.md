# Staff Graded Assignment XBlock

This package provides an XBlock for use with the open edX platform which
provides a staff graded assignment. Students are invited to upload files
which encapsulate their work on the assignment. Instructors are then
able to download the files and enter grades for the assignment.

Note that this package is both an XBlock and a Django application.

## Installation

### Devstack installation (for local development)

Since this involves changing version-controlled files in `edx-platform`, it's a good idea to create
a branch in that repo for all SGA development. **All of the edits below refer to `edx-platform` files or
configuration files in devstack. No files in the `edx-sga` repo need to be edited to install and use
the SGA XBlock in devstack.**

1. **Configure file storage**

    For file storage, SGA uses the same file storage configuration as other
    applications in edX, such as the comments server.
    devstack defaults to local storage, and fullstack defaults to
    S3. Using local file storage is the easiest option for hacking on and debugging SGA locally.

    To configure SGA to use local storage, edit `lms/envs/private.py`
    to include these settings (and create the file if it doesn't exist yet):
    
    Starting with Django 4.2, the `get_storage_class` function has been deprecated and is scheduled
    for removal in Django 5.2. To ensure forward compatibility, Django has introduced a new 
    storages system. You can now define all your custom or third-party storage backends using
    the STORAGES dictionary in your settings. 
    
    Do not use both DEFAULT_FILE_STORAGE and STORAGES in your settings.
    They are mutually exclusive, and you should use only one of these options.

    ```
    MEDIA_ROOT = "/edx/var/edxapp/uploads"
   
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    or
    STORAGES = {
        # The default file storage backend (fallback for user-uploaded media, etc.)
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
    
        # Static files storage (used by collectstatic etc.)
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    
        # Your SGA-specific storage backend
        "sga_storage": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {
                "bucket_name": "sga",
                "default_acl": "public-read",
                "location": "sga/images",
            },
        },
    }
    ```

    You can also configure S3 to be used as the file storage backend. Ask a fellow developer or devops for the
    correct settings to enable this. If you're using ansible to provision devstack, you may want to refer to 
    [this edX article on configuring data storage](https://openedx.atlassian.net/wiki/spaces/OpenOPS/pages/112001105/Configuring+Data+Storage).
    
1. **Add SGA to the Advanced Module List for your course in Studio**
   
    Open Advanced Settings for your course in Studio ("Settings" drop down in the top nav > "Advanced Settings"), 
    and add `"edx_sga"` to the "Advanced Module List" value (i.e.: the value for "Advanced Module List" should 
    be a JSON list, and that list should include `"edx_sga"`).

1. **If necessary, add SGA to installed Django apps**

    **NOTE:** This is only needed if `edx_sga` is not somehow included in `INSTALLED_APPS` already. In
    edx-platform, an app can make its way into `INSTALLED_APPS` in a few different ways, so the easiest thing
    to do is grep your edx-platform branch for 'edx_sga' and see if it appears in `INSTALLED_APPS`/`OPTIONAL_APPS`/etc.
    **All releases of edx-platform since Dogwood already include `edx_sga`, so this step is likely unnecessary.**

    If SGA is not already an installed app, add this as a top-level setting in `/edx/app/edxapp/lms.env.json` and 
    `/edx/app/edxapp/cms.env.json`:

    ```
    "ADDL_INSTALLED_APPS": ["edx_sga"],
    ```

    Also in `/edx/app/edxapp/cms.env.json`, add this to the `FEATURES` object:

    ```
    "ALLOW_ALL_ADVANCED_COMPONENTS": true,
    ```

1. **Add the package as a dependency (or install manually)**

    If you want devstack to install a local branch of `edx-sga` and use any local changes that you make, you'll need 
    to do the following:
    
    1. Find any requirements files that list an `edx-sga` dependency and comment out those lines (there are many 
    requirements files in the `edx-platform` repo, and they're all `.txt` files, as is convention with pip). Note that
    the app as it's recognized by Django is `edx_sga` with an underscore, but the repo is `edx-sga` with a dash.
    
    1. Sync/mount your `edx-sga` repo directory to the Docker container or Vagrant VM (depending on which method you 
    use to run devstack on your machine).
        - In Vagrant, you can add this to the `Vagrantfile` within the `Vagrant.configure` block (after running
        `vagrant up` or `vagrant reload`, the directory will be mounted).:

            ```
            config.vm.synced_folder '/path/to/your/edx-sga', '/edx/app/edxapp/venvs/edxapp/src/edx-sga/', create: true, owner: 'edxapp', group: 'edxapp'
            ```
            
    1. Add the mounted `edx-sga` repo directory as a dependency in `requirements/private.txt` 
    (creating the file if necessary):

        ```
        -e /edx/app/edxapp/venvs/edxapp/src/edx-sga
        ```
    
    You should now be able to work with SGA blocks when you run LMS or Studio, and any local changes you make to SGA 
    should be seen if you restart the server.
        
    If the steps above don't suit your purposes (or they simply don't work), you may also try installing SGA manually 
    (*NOTE: These are old instructions*):

    ```sh
    sudo su - edxapp -s /bin/bash
    . edxapp_env
    pip install -e git+https://github.com/mitodl/edx-sga@release#egg=edx-sga
    ```

### Production Installation

Create a branch of edx-platform to commit a few minor changes:

1. **Add SGA to the platform requirements**

    In `requirements/edx/github.txt`, add:

    ```
    -e git+https://github.com/mitodl/edx-sga@release#egg=edx-sga
    ```

1. **Add appropriate `edx_sga` settings**

    - In both `cms/envs/common.py` and `lms/envs/common.py`, 
    add `'edx_sga'` to `OPTIONAL_APPS`
    - In `cms/envs/common.py`, add `'edx_sga'` to `ADVANCED_COMPONENT_TYPES`

1. **Configure file storage**

    In production, the edx-platform uses S3 as the default storage
    engine. If you want to use file storage see the devstack/full
    instructions above.  To configure S3 storage properly in the
    platform, set the following values in your
    `/edx/app/edxapp/lms.auth.json` file or, preferably, in your
    additional yaml overrides in your edx/configuration setup.

    ```
    "AWS_ACCESS_KEY_ID": "your bucket AWS access key ID",
    "AWS_SECRET_ACCESS_KEY": "Your bucket AWS access key secret",
    "AWS_STORAGE_BUCKET_NAME": "Your upload bucket name",
    ```

## Course Authoring in edX Studio

1. Change Advanced Settings

    1. Open a course you are authoring and select "Settings" ⇒ "Advanced
       Settings
    2. Navigate to the section titled "Advanced Module List"
    3. Add "edx\_sga" to module list.
    4. Studio should save your changes automatically.

    ![The Advanced Module List section in Advanced Settings](https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-studio-advanced-settings.png)

2. Create an SGA XBlock

    1. Return to the Course Outline
    2. Create a Section, Sub-section and Unit, if you haven't already
    3. In the "Add New Component" interface, you should now see an "Advanced"
      button
    4. Click "Advanced" and choose "Staff Graded Assignment"

    ![buttons for problems types, including advanced types](https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-studio-new-unit.png)

3. Write a question with an SGA response

    Since the Staff Graded Assignment doesn't support text within the problem,
    it is recommended to precede the SGA XBlock with a Text or HTML XBlock with
    instructions for the student. We recommend something using the following
    template:

    ```
    Use the "Select a File" button below to choose the file you wish to have
    graded. After you have chosen the file the button will change to the
    name of the file. Click the button again to Upload.

    When the upload is complete, a link will appear with the name of your
    file. Click it to confirm that the upload was successful. You can replace
    this file by simply selecting another file and uploading it. After
    the due date has passed, you will no longer be able to upload files.
    ```

    Note that *any* file type can be uploaded. If you expect a particular file
    type from your students, you should specify it in the instructions. If you
    wish students to upload multiple files, you can recommend they zip the
    files before uploading.

4. Settings

  - **display_name**: The name appears in the horizontal navigation at the top of the page
  - **Maximum Score**: Maximum grade score given to assignment by staff
  - **Problem Weight**: Defines the number of points each problem is worth.
  - **Show Answer**: Specifies if and when the student will see the correct answer to the problem.
  - **Solution**: The solution that is shown to the student if Show Answer is enabled for the problem. 
  
    ![sga settings](https://user-images.githubusercontent.com/8322892/36798686-48c41bc6-1c79-11e8-9ffb-d90a0169e69d.png)

5. Grading Policy

    SGA XBlocks inherit grading settings just like any other problem type. You
    can include them in homework, exams or any assignment type of your choosing.

## Course Authoring in XML

XML for an SGA XBlock consists of one tag with the five attributes mentioned
above. It is recommended to also include a url_name attribute. For example:

```xml
<vertical display_name="Staff Graded Assignment">
    <edx_sga url_name="sga_example" weight="10.0" display_name="SGA Example" points="100.0" showanswer="past_due" solution="solution text" />
</vertical>
```
You can specify the following values for the show answer attribute.
* always
* answered
* attempted
* closed
* correct_or_past_due
* finished
* past_due
* never

## Staff Grading

1. Navigate to the student view (LMS) of the course and find the vertical with
    your Staff Graded Assignment. (If you are in Studio, click "View Live").

1. If you are Course Staff or an Instructor for the course, you will see a
    "Grade Submissions" button in the lower right corner of the XBlock (Be sure
    you are in "Staff View" indicated by a red label in the upper right corner of
    the page; if it says "Student View" in green, click on it once.)

    ![Staff view of LMS interface](https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-lms-before-upload.png)

1. When you click "Grade Submissions" a grid of student submissions will display
    in a lightbox. Columns for username, (full) name, Filename and Uploaded
    (time) will be filled in.

    ![Staff view of grading grid](https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-staff-grading-interface.png)

1. Click the filename in any row to download the student's submission. If it can
    be displayed in your browser, it will.

1. Click the **Enter grade** link to bring up an interface to enter grades and
    comments.

    ![Enter grade interface](https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-staff-enter-grade.png)

1. The grades and comments will appear in the grid. Use the "Upload Annotated
    File" button to upload a file in response to the student's submission. The
    student will be able to view the file along with her grade.

    ![Instructor view of grading grid after a submission has been graded.](https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-graded.png)

1. Course staff can enter grades, but they are not final and students won't see
    them until they are submitted by an instructor. When a grade is waiting for
    instructor approval, it appears in the submissions grid with the text
    `(Awaiting instructor approval)` after it.

    ![Detail of Staff Member view of grading grid after a submission has been graded and it is awaiting approval.](https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-awaiting-approval.png)

    After a course staff member has submitted a grade, the instructor will see a
    link to **Approve grade** instead of **Enter grade**.

    ![Detail of Instructor view of grading grid after a submission has been graded and it can be appproved.](https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-approve-grade.png)

    Clicking **Approve grade** will open the same grading dialog box where, in
    addition to approving the grade, she can change the grade and the comment.

    Once the instructor has approved or entered a grade, course staff members
    cannot change it. However, the instructor can always change a grade.

1. After the grade has been approved, the student will be able to see it inline
    and also in her progress page. Annotated files, if any, will be available
    for download.

    ![Student view of graded assignment with annotated instructor response](https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-lms-student-video-graded.png)

## Translations (Atlas / Tutor)

`edx_sga/conf/locale` is the canonical source directory for translation
catalogues. `edx_sga/translations` points to it for the XBlock runtime, while
`edx_sga/locale` preserves Django's standard catalogue discovery for this
package, which is both an XBlock and a Django app.

To update the source catalogues, install `i18n-tools` and run:

```sh
make extract_translations
```

For Atlas, the corresponding catalogues belong in `openedx-translations` at:

```
translations/edx-sga/edx_sga/conf/locale/<locale>/LC_MESSAGES/
```

Use `django.po` for Python and Django templates. SGA also uses JavaScript
`gettext`, so include `djangojs.po` for a fully translated interface. Tutor
pulls and compiles these files from `openedx-translations` while building the
`openedx` image; this repository's Makefile is for local extraction and
validation.

## Testing

Assuming `edx-sga` is installed as above, integration tests can be run in devstack with this command:

```sh
python manage.py lms --settings=test test edx_sga.tests.integration_tests
```

To run tests on your host machine (with a mocked edX platform):
    
```sh
# Run tests using different versions of Django
tox
# Run tests using a specific version of Django
tox -e py27-django111
```

To get statement coverage (in devstack):

```sh
coverage run --source edx_sga manage.py lms --settings=test test edx_sga.tests.integration_tests
coverage report -m
```
