Introduction
============

This recipe is based on `collective.recipe.plonesite`_. It provides recipes for creating and updating Plone sites, running scripts against Plone sites and for setting their properties. If you use zeoserver, all the recipes will start and stop zeo appropriately (not stopping it if it wasnt the process that started it, for example). When combined with `isotoma.recipe.zope2instance` it can properly deal with errors, ending the buildout run rather than continuing and succeeding.

.. _`collective.recipe.plonesite`: http://pypi.python.org/pypi/collective.recipe.plonesite
.. _`isotoma.recipe.zope2instance`: http://pypi.python.org/pypi/isotoma.recipe.zope2instance


Managing plone sites
====================

This recipe enables you to create and update a Plone site as part of a buildout run.  This recipe only aims to run profiles and Quickinstall products.  It is assumed that the install methods, setuphandlers, upgrade steps, and other recipes will handle the rest of the work.

To use it, add something like this to your recipe::

    [plonesite]
    recipe = isotoma.recipe.plonetools:site
    products =
        LinguaPlone
        iw.fss
        you.YourProduct

Parameters
----------

.. [1] Profiles have the following format: ``<package_name>:<profile>`` (e.g. ``my.package:default``).  The profile can also be prepended with the ``profile-`` if you so choose (e.g. ``profile-my.package:default``).

.. [2] The product name is typically **not** the package name such as `Products.MyProduct`, but just the product name `MyProduct`. Quickest way to find out the name that is expected is to 'inspect' the Quickinstaller page and see what value it is passing in.

site-id
    The id of the Plone site that the script will create.  This will also be used to update the site once created.  Default: Plone

admin-user
    The id of an admin user that will be used as the 'Manager'.  Default: admin

products-initial
    A list of products to quickinstall just after initial site creation. See above for information about the product name format [2]_.

profiles-inital
    A list of GenericSetup profiles to run just after initial site creation. See above for informaion on the expected profile id format [1]_.

products
    A list of products to quickinstall each time buildout is run. See above for information about the product name format [2]_.

profiles
    A list of GenericSetup profiles to run each time buildout is run. See above for informaion on the expected profile id format [1]_.

instance
    The name of the instance that will run the script. Default: instance

zeoserver
    The name of the zeoserver part that should be used.  This is only required if you are using a zope/zeo setup. Default: not set

before-install
    A system command to execute before installing Plone.  Optional.  You could use this to start a Supervisor daemon to launch ZEO, instead of launching ZEO directly.  You can use this option in place of the zeoserver option.

after-install
    A system command to execute after installing Plone.  Optional.

site-replace
    Replace any existing plone site named site-id. Default: false

enabled
    Option to start up the instance/zeoserver.  Default: true.  This can be a useful option from the command line if you do not want to start up Zope, but still want to run the complete buildout.

    $ bin/buildout -Nv plonesite:enabled=false

pre-extras
    An absolute path to a file with python code that will be evaluated before running Quickinstaller and GenericSetup profiles.  Multiple files can be given.  Two variables will be available to you.  The app variable is the zope root.  The portal variable is the plone site as defined by the site-id option. NOTE: file path cannot contain spaces. Default: not set

post-extras
    An absolute path to a file with python code that will be evaluated after running Quickinstaller and GenericSetup profiles.  Multiple files can be given.  Two variables will be available to you.  The app variable is the zope root.  The portal variable is the plone site as defined by the site-id option. NOTE: file path cannot contain spaces. Default: not set


Setting properties
==================

This recipe lets you set properties for a Plone site as part of a buildout run.

To use this, add something like this to your recipe::

    [setproperties]
    recipe = isotoma.recipe.plonetools:properties
    properties = {
        "somestring": "${some:string}",
        "somebool": True,
        "somelist": [1, 2, 3,4 ],
        }

Mandatory parameters
--------------------

properties
    A set of properties as JSON


Running commands
================

This recipe lets you run a script against a Plone site as part of a buildout run.

To use this, add something like this to your recipe::

    [runscript]
    recipe = isotoma.recipe.plonetools:script
    command = /path/to/script.py --site-id=Plone --other-param=${foo:bar}

Mandatory parameters
--------------------

command
    The script to execute, and the arguments to pass to it


Creating wrapper scripts
========================

This recipe lets you create a script in your buildouts bin-directory to run a script for you under the correct
zope instance.

To use this, add something like this to your recipe::

    [instance]
    recipe = isotoma.recipe.zope2instance
    otherprops = here

    [wrappers]
    recipe = isotoma.recipe.plonetools:wrapper
    instance = instance
    entry-points =
       myscript=mypackage.myscript:run

Mandatory parameters
--------------------

entry-points
    A list of entry points in the form name=module.function

Optional parameters
-------------------

instance
    The name of a zope2instance part. Default: instance.

instance-script
    The full path to a zopectl or zope2instance script. By default it looks in your buildout bin-directory for instance.


