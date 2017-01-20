Staff Graded Assignment XBlock
==============================

This package provides an XBlock for use with the edX platform which
provides a staff graded assignment. Students are invited to upload files
which encapsulate their work on the assignment. Instructors are then
able to download the files and enter grades for the assignment.

Note that this package is both an XBlock and a Django application. 

Installation
------------


Try Out on devstack/fullstack
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Install Package 

   installing manually for evaluation and testing:

   -  ``sudo su - edxapp -s /bin/bash``
   -  ``. edxapp_env``
   -  ``pip install -e git+https://github.com/mitodl/edx-sga@release#egg=edx-sga``

2. Add edx\_sga to installed Django apps

   - In ``/edx/app/edxapp/lms.env.json`` and ``/edx/app/edxapp/cms.env.json``, add 

	 .. code:: javascript

	     "ADDL_INSTALLED_APPS": ["edx_sga"],

     on the second line right after ``{``

   - In ``/edx/app/edxapp/cms.env.json``, add

	 .. code:: javascript

          "ALLOW_ALL_ADVANCED_COMPONENTS": true,

     to the list of ``FEATURES``

3. Configure file storage

   For file storage, SGA uses the same file storage configuration as other
   applications in edX, such as the comments server. If you change these
   settings to SGA it will also affect those other applications.

   devstack defaults to local storage, but fullstack defaults to
   S3. To configure local storage:
   
   1. Use local storage (useful for evaluation and testing)
   
      In ``/edx/app/edxapp/edx-platform/lms/envs/aws.py`` change:
      
      .. code:: sh

          DEFAULT_FILE_STORAGE = 'storages.backends.s3boto.S3BotoStorage'
      
      to:
      
      .. code:: sh

          DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
          MEDIA_ROOT = '/edx/var/edxapp/uploads'

Production Installation
~~~~~~~~~~~~~~~~~~~~~~~

Create a branch of edx-platform to commit a few minor changes:

1. Add SGA to the platform requirements
	
   - In ``/edx/app/edxapp/edx-platform/requirements/edx/github.txt``, add:
   
     .. code:: sh
   
          -e git+https://github.com/mitodl/edx-sga@release#egg=edx-sga

2. Add edx\_sga to installed Django apps

   - In ``/edx/app/edxapp/edx-platform/cms/envs/common.py``, add ``'edx_sga'``
     to OPTIONAL_APPS

   - In ``/edx/app/edxapp/edx-platform/lms/envs/common.py``, add ``'edx_sga'``
     to OPTIONAL_APPS

3. Enable the SGA component in LMS and Studio (CMS).

   -  In ``/edx/app/edxapp/edx-platform/cms/envs/common.py``, add ``'edx_sga',`` to ``ADVANCED_COMPONENT_TYPES``:

          
4. Configure file storage

   In production, the edx-platform uses S3 as the default storage
   engine. If you want to use file storage see the devstack/full
   instructions above.  To configure S3 storage properly in the
   platform, set the following values in your
   ``/edx/app/edxapp/lms.auth.json`` file or, preferably, in your
   additional yaml overrides in your edx/configuration setup.

      .. code:: sh

          "AWS_ACCESS_KEY_ID": "your bucket AWS access key ID",
          "AWS_SECRET_ACCESS_KEY": "Your bucket AWS access key secret",
          "AWS_STORAGE_BUCKET_NAME": "Your upload bucket name",

Course Authoring in edX Studio
------------------------------

1. Change Advanced Settings

   1. Open a course you are authoring and select "Settings" ⇒ "Advanced
      Settings
   2. Navigate to the section titled "Advanced Module List"
   3. Add "edx\_sga" to module list.
   4. Studio should save your changes automatically.
   
.. figure:: https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-studio-advanced-settings.png
   :alt: the Advanced Module List section in Advanced Settings
   
2. Create an SGA XBlock

   1. Return to the Course Outline
   2. Create a Section, Sub-section and Unit, if you haven't already
   3. In the "Add New Component" interface, you should now see an "Advanced" 
      button
   4. Click "Advanced" and choose "Staff Graded Assignment"

.. figure:: https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-studio-new-unit.png
   :alt: buttons for problems types, including advanced types


3. Write a question with an SGA response

   Since the Staff Graded Assignment doesn't support text within the problem, 
   it is recommended to precede the SGA XBlock with a Text or HTML XBlock with 
   instructions for the student. We recommend something using the following 
   template:
   
       Use the "Select a File" button below to choose the file you wish to have 
       graded. After you have chosen the file the button will change to the 
       name of the file. Click the button again to Upload.
       
       When the upload is complete, a link will appear with the name of your 
       file. Click it to confirm that the upload was successful. You can replace
       this file by simply selecting another file and uploading it. After
       the due date has passed, you will no longer be able to upload files. 
   
   Note that *any* file type can be uploaded. If you expect a particular file
   type from your students, you should specify it in the instructions. If you
   wish students to upload multiple files, you can recommend they zip the
   files before uploading. 

4. Settings

+----------------+--------------------------------------------------------------------------+
| display_name   | The name appears in the horizontal navigation at the top of the page     |
+----------------+--------------------------------------------------------------------------+
| Maximum Score  | Maximum grade score given to assignment by staff                         |
+----------------+--------------------------------------------------------------------------+
| Problem Weight | Defines the number of points each problem is worth.                      |
+----------------+--------------------------------------------------------------------------+

.. figure:: https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-studio-editing-sga.png
   :alt: Editing SGA Settings

5. Grading Policy

   SGA XBlocks inherit grading settings just like any other problem type. You 
   can include them in homework, exams or any assignment type of your choosing.  
       
Course Authoring in XML
-----------------------

XML for an SGA XBlock consists of one tag with the three attributes mentioned
above. It is recommended to also include a url_name attribute. For example:

.. code:: XML

        <vertical display_name="Staff Graded Assignment">
            <edx_sga url_name="sga_example" weight="10.0" display_name="SGA Example" points="100.0" />
        </vertical>


Staff Grading
-------------

#. Navigate to the student view (LMS) of the course and find the vertical with 
   your Staff Graded Assignment. (If you are in Studio, click "View Live"). 
   
#. If you are Course Staff or an Instructor for the course, you will see a 
   "Grade Submissions" button in the lower right corner of the XBlock (Be sure 
   you are in "Staff View" indicated by a red label in the upper right corner of
   the page; if it says "Student View" in green, click on it once.)
   
   .. figure:: https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-lms-before-upload.png
      :alt: Staff view of LMS interface

#. When you click "Grade Submissions" a grid of student submissions will display
   in a lightbox. Columns for username, (full) name, Filename and Uploaded
   (time) will be filled in.

   .. figure:: https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-staff-grading-interface.png
      :alt: Staff view of grading grid

#. Click the filename in any row to download the student's submission. If it can
   be displayed in your browser, it will.

#. Click the **Enter grade** link to bring up an interface to enter grades and
   comments.

   .. figure:: https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-staff-enter-grade.png
      :alt: Enter grade interface

#. The grades and comments will appear in the grid. Use the "Upload Annotated
   File" button to upload a file in response to the student's submission. The
   student will be able to view the file along with her grade.

   .. figure:: https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-graded.png
      :alt: Instructor view of grading grid after a submission has been graded.

#. Course staff can enter grades, but they are not final and students won't see 
   them until they are submitted by an instructor. When a grade is waiting for 
   instructor approval, it appears in the submissions grid with the text 
   :code:`(Awaiting instructor approval)` after it. 
   
   .. figure:: https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-awaiting-approval.png
      :alt: Detail of Staff Member view of grading grid after a submission has been graded and it is awaiting approval.

   After a course staff member has submitted a grade, the instructor will see a
   link to **Approve grade** instead of **Enter grade**. 
   
   .. figure:: https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-approve-grade.png
      :alt: Detail of Instructor view of grading grid after a submission has been graded and it can be appproved. 
   
   Clicking **Approve grade** will open the same grading dialog box where, in 
   addition to approving the grade, she can change the grade and the comment.

   Once the instructor has approved or entered a grade, course staff members
   cannot change it. However, the instructor can always change a grade.


#. After the grade has been approved, the student will be able to see it inline
   and also in her progress page. Annotated files, if any, will be available
   for download.

   .. figure:: https://raw.githubusercontent.com/mitodl/edx-sga/screenshots/img/screenshot-lms-student-video-graded.png
      :alt: Student view of graded assignment with annotated instructor response

Testing
-------

Assuming ``edx-sga`` is installed as above, you can run tests like so::
    
    $ python manage.py lms --settings=test test edx_sga

To get statement coverage::

    $ coverage run --source edx_sga manage.py lms --settings=test test edx_sga
    $ coverage report -m
