SGA 0.5.0 Release Notes
=======================

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
