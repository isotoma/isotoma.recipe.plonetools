# -*- coding: utf-8 -*-
"""Recipe plonesite"""

import os
import sys
import subprocess
import pkg_resources
from zc.buildout import UserError

TRUISMS = [
    'yes',
    'y',
    'on',
    'true',
    'sure',
    'ok',
    '1',
]

def system(c):
    if os.system(c):
        raise SystemError("Failed", c)

class Recipe(object):
    """zc.buildout recipe"""

    def __init__(self, buildout, name, options):
        self.buildout, self.name, self.options = buildout, name, options
        options['location'] = os.path.join(
            buildout['buildout']['parts-directory'],
            self.name,
            )
        # suppress script generation.
        self.options['scripts'] = ''
        options['bin-directory'] = buildout['buildout']['bin-directory']
        
        # all the options that will be passed on to the 'run' script
        self.site_id = options.get('site-id', 'Plone')
        self.site_replace = options.get('site-replace', '').lower() in TRUISMS
        self.admin_user = options.get('admin-user', 'admin')
        self.products_initial = options.get('products-initial', "").split()
        self.profiles_initial = options.get('profiles-initial', "").split()
        self.products = options.get('products', "").split()
        self.profiles = options.get('profiles', "").split()
        self.post_extras = options.get('post-extras', "").split()
        self.pre_extras = options.get('pre-extras', "").split()
        options['args'] = self.createArgs()
        
        # We can disable the starting of zope and zeo.  useful from the
        # command line:
        # $ bin/buildout -v plonesite:enabled=false
        self.enabled = options.get('enabled', 'true').lower() in TRUISMS
        
        # figure out if we need a zeo server started, and if it's on windows
        # this code was borrowed from plone.recipe.runscript
        is_win = sys.platform[:3].lower() == "win"
        # grab the 'instance' option and default to 'instance' if it does not exist
        instance = buildout[options.get('instance', 'instance')]
        instance_home = instance['location']
        instance_script = os.path.basename(instance_home)
        if is_win:
            instance_script = "%s.exe" % instance_script
        options['instance-script'] = instance_script
        self.zeoserver = options.get('zeoserver', False)
        if self.zeoserver:
            if is_win:
                zeo_script = 'zeoservice.exe'
            else:
                zeo_home = buildout[self.zeoserver]['location']
                zeo_script = os.path.basename(zeo_home)
            options['zeo-script'] = zeo_script
        self.before_install = options.get('before-install')
        self.after_install = options.get('after-install')

    def install(self):
        """
        1. Run the before-install command if specified
        2. Start up the zeoserver if specified
        3. Run the script
        4. Stop the zeoserver if specified
        5. Run the after-install command if specified
        """
        options = self.options
        # XXX is this needed?
        location = options['location']
        if self.enabled:

            if self.before_install:
                system(self.before_install)
            if self.zeoserver:
                zeo_cmd = "%(bin-directory)s/%(zeo-script)s" % options
                zeo_start = "%s start" % zeo_cmd
                subprocess.call(zeo_start.split())

            # XXX This seems wrong...
            options['script'] = pkg_resources.resource_filename(__name__, 'plonesite.py')
            # run the script
            cmd = "%(bin-directory)s/%(instance-script)s run %(script)s %(args)s" % options
            result = subprocess.call(cmd.split())
            if result > 0:
                raise UserError("Plone script could not complete")

            if self.zeoserver:
                zeo_stop = "%s stop" % zeo_cmd
                subprocess.call(zeo_stop.split())
            if self.after_install:
                system(self.after_install)

        return location

    def update(self):
        """Updater"""
        self.install()

    def createArgs(self):
        """Helper method to create an argument list
        """
        args = []
        args.append("--site-id=%s" % self.site_id)
        # only pass the site replace option if it's True
        if self.site_replace:
            args.append("--site-replace")
        args.append("--admin-user=%s" % self.admin_user)
        def createArgList(arg_name, arg_list):
            if arg_list:
                for arg in arg_list:
                    args.append("%s=%s" % (arg_name, arg))
        createArgList('--pre-extras', self.pre_extras)
        createArgList('--post-extras', self.post_extras)
        createArgList('--products-initial', self.products_initial)
        createArgList('--products', self.products)
        createArgList('--profiles-initial', self.profiles_initial)
        createArgList('--profiles', self.profiles)
        return " ".join(args)
