Release Notes
=============

Version 0.12.0 (Released October 07, 2020)
--------------

- Allow a grade of zero
- removed deprecated usage of xblock fragment (#270)
- Fix mismatch version (#272)

Version 0.11.1 (Released August 12, 2020)
--------------

- Fix mismatch version (#272)

Version 0.11.0 (Released May 19, 2020)
--------------

- Temporarily disable integration and Python 2 tests (#267)
- Added missing decode to resource loading
- Fixed build error involving jsonfield import in edx-submissions

Version 0.10.0 (Released October 28, 2019)
--------------

- Ran python-modernizer on repo (#256)

Version 0.9.0 (Released October 01, 2019)
-------------

- Possible fix for copying units with SGA (#254)
- Correct the courseware imports
- Added focus to file upload error message (#241)
- Recreated submissions zip file when student(s) score reset (#239)
- Fixed race condition when removing grades SGA (#117)

Version 0.8.3 (Released August 22, 2018)
-------------

- Fix integration tests under Django 1.11 (#247)

Version 0.8.2 (Released April 30, 2018)
-------------

- Release 0.8.1
- Added tests to validate all student submissions (#235)
- Added url encoding in file name (#236)
- Added support email to the error message on zip submissions download (#234)
- Fixed comma in file name (#237)
- Fixed Django 1.11 related issue in test (#238)
- Fixed zipping large files for staff submissions. (#226) (#230)
- Fixed zipping large files for staff submissions. (#226)
- Update README.md
- Update README.md

Version 0.8.1 (Released March 20, 2018)
-------------

- Added tests to validate all student submissions (#235)
- Added url encoding in file name (#236)
- Added support email to the error message on zip submissions download (#234)
- Fixed comma in file name (#237)
- Fixed Django 1.11 related issue in test (#238)
- Fixed zipping large files for staff submissions. (#226) (#230)
- Fixed zipping large files for staff submissions. (#226)
- Update README.md
- Update README.md

Version 0.8.0 (Released February 13, 2018)
-------------

- Cleaned up zip file creation and retrieval code
- Update README.md
- Update README.md
- Handle static_asset_path setting (#223)
- Added logic to clear a user&#39;s state in the XBlock
- Replace static links when rendering solution text (#217)
- Updated readme (updated installation/usage details, changed format to .md)
- Fixed file modified time calculation for submission zip file
- Enable zip file creation using S3 or local file storage
- Serialize and parse solution as an XML element, if valid XML (#211)
- Move ShowAnswerXBlockMixin into SGA (#208)
- Add support for graceperiod (#207)
- Use UTC for timestamp (#206)
- Upload coverage to codecov (#201)
- Fix tests (#203)
- Clean tests (#200)
- Reordered XBlock class methods
- Integrate ShowAnswerXBlockMixin (#197)
- Fixed submission download bug
- Use StudioEditableXBlockMixin (#190)
- Run integration tests on travis (#194)
- Add download all submissions (#187)
- Separated upload and submit buttons in student submission upload UI
- add pull request template (#193)
- Revert xblock-utils library (#192)
- Add mitodl/xblock-utils as dependency (#189)
- Add travis.yml (#188)

Version 0.7.1 (Released November 07, 2017)
-------------

- Reference __init__ version (#180)
- Release 0.7.0
- Added new tests with mocking data (#174)
- Changed ugettext to ugettext_lazy (#178)
- Replace hard coded strings to be translatable in the future (i10n) (#175)
- Converted SGA into django app and added tox base testing (#170)
- Use the timezone of the platform as opposed to UTC for submissions&#39; dates (#169)
- Increase the height of the &quot;Select a File&quot; element (#165)

Version 0.7.0 (Released November 07, 2017)
-------------

- Added new tests with mocking data (#174)
- Changed ugettext to ugettext_lazy (#178)
- Replace hard coded strings to be translatable in the future (i10n) (#175)
- Converted SGA into django app and added tox base testing (#170)
- Use the timezone of the platform as opposed to UTC for submissions&#39; dates (#169)
- Increase the height of the &quot;Select a File&quot; element (#165)

Version 0.6.4 (Released July 27, 2017)
-------------

- Serialize block/course locators before sending to submissions API. (#166)

Version 0.6.3 (Released May 03, 2017)
-------------

- preface id refs with strings, add tabindex to modals (#163)

Version 0.6.1 (Released February 13, 2017)
-------------

- Fixed error "ValueError: invalid literal for int() with base 10: 'undefined'" (#160)
- Fixed typo in README (#158)

Version 0.6.0 (Released November 16, 2016)
-------------

- adding version number so this will work with our release-script
- Fixed test failure issues on sga (#146)
- Removed import in __init__
- Center modal and fix scrolling
- Installed bower with URI.js, require.js, underscore, jquery
- Add actions cell to assignments table header.
- Added basic developer notes.
- Added sorting plugin to header table, Now you can sort each column by clicking header
- Handle file not found error, Fixed error messages, set error code to 404
- Allow not only english language file uploads
- Implement support for multiply SGA elements at one vertical
- fixed all posible pylint issues
- fix jshint indentified issue for all studio and edx_sga file
- merge base and fixed error message display under button error and loaded max file size from settings
- Added log.info in all locations where sga.py is chaning state of StudentModule
- added display name on sga lms and grade submission dialog
- Changed enter grade link style to make it look like button and added some spaces in css attributes
- Added weight validations and test cases, split long length test into sub funtions
- Design changes in sga settings page, added a settings tab and style in css file, added some classes

Migrations
----------

0.5.0 uses the edX Submissions API to submit grades. If you are upgrading from an 
version before 0.4.0 and you have student submissions and grades that need to be migrated, 
you should run the migration script. 

.. code-block:: bash

  python manage.py lms --settings=aws sga_migrate_submissions DevOps/0.001/2015_Summer
  
NOTE: After applying this update, you may need to change max_score on SGA 
problems to an integer.   

Additions
---------

- Validates max_score and grades to ensure they are non-negative integers
- Works with split mongo
- Added Staff Debug

Fixes
-----

no fixes in this release
