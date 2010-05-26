# -*- coding: utf-8 -*-

"""
I provide 4 recipes for building and managing a plone site.

 * Site takes care of creating portals and running quickinstall
 * Properties lets you set properties on a portal object
 * Command makes it easy to run a script under the right zope 2 instance as part of buildout
 * Wrapper makes it easy to create a wrapper that runs a script under the right zope 2 instance
"""

import os, sys, re, subprocess
import pkg_resources
from zc.buildout import UserError
import simplejson as json
import shlex

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
    p = subprocess.Popen(c, shell=True)
    sts = os.waitpid(p.pid, 0)[1]
    if sts != 0:
        raise SystemError("Failed", c)

class Recipe(object):

    """
    I am a base class for recipes that want to start zeo (if applicable), run a script
    and make sure that zeo is shutdown at the end (but only when I started it).
    """

    def __init__(self, buildout, name, options):
        self.buildout, self.name, self.options = buildout, name, options
        options['location'] = os.path.join(
            buildout['buildout']['parts-directory'],
            self.name,
            )

        self.installed = []
        self.stop_zeo = False
        self.bin_directory = buildout['buildout']['bin-directory']

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
        self.instance_script = instance_script

        self.zeoserver = options.get('zeoserver', False)
        if self.zeoserver:
            if is_win:
                zeo_script = 'zeoservice.exe'
            else:
                zeo_home = buildout[self.zeoserver]['location']
                zeo_script = os.path.basename(zeo_home)

            options.setdefault("zeo-script", os.path.join(self.bin_directory, zeo_script))
            options.setdefault("zeo-pid-file", os.path.join(buildout['buildout']['directory'], "var", "%s.pid" % self.zeoserver))

    def is_zeo_started(self):
        # Is there a PID file?
        pid_file = self.options["zeo-pid-file"]
        if not os.path.exists(pid_file):
            return False

        # Read PID file, make sure its an int
        pid = open(pid_file).read().strip()
        try:
            pid = int(pid)
        except:
            return False

        # Try kill() with signal 0
        # No exceptions means the zeoserver is running
        #  Special case: if we dont have permissions, give up
        try:
            os.kill(pid, 0)
            return True
        except OSError, e:
            if e.errno == 3:
                raise UserError("We don't have permission to check the status of that zeoserver")

        return False

    def install(self):
        """
        1. Run the before-install command if specified
        2. Start up the zeoserver if specified
        3. Run the script
        4. Stop the zeoserver if specified
        5. Run the after-install command if specified
        """

        # XXX is this needed?
        self.installed.append(self.options['location'])

        if self.enabled:

            if self.zeoserver and not self.is_zeo_started():
                zeo_start = "%s start" % self.options["zeo-script"]
                subprocess.call(zeo_start.split())
                self.stop_zeo = True

            try:
                # work out what to run
                cmd = "%(bin-directory)s/%(instance-script)s run %(command)s" % {
                    "bin-directory": self.bin_directory,
                    "instance-script": self.instance_script,
                    "command": self.get_command(),
                    }

                # run the script
                result = subprocess.call(shlex.split(cmd))
                if result > 0:
                    raise UserError("Plone script could not complete")
            finally:
                if self.stop_zeo:
                    zeo_stop = "%s stop" % self.options["zeo-script"]
                    subprocess.call(zeo_stop.split())

        return self.installed

    def get_internal_script(self, scriptname):
        return pkg_resources.resource_filename(__name__, scriptname)

    def update(self):
        """Updater"""
        self.install()


class Site(Recipe):

    """
    I create a plone site and run quickinstall
    """

    def install(self):
        before_install = self.options.get("before-install", None)
        if before_install:
           system(before_install)

        super(Site, self).install()

        after_install = self.options.get("after-install", None)
        if after_install:
            system(after_install)

        return self.installed

    def get_command(self):
        o = self.options.get

        args = []
        args.append("--site-id=%s" % o("site-id", "Plone"))
        # only pass the site replace option if it's True
        if o('site-replace', '').lower() in TRUISMS:
            args.append("--site-replace")
        args.append("--admin-user=%s" % o("admin-user", "admin"))

        def createArgList(arg_name, arg_list):
            if arg_list:
                for arg in arg_list:
                    args.append("%s=%s" % (arg_name, arg))

        createArgList('--pre-extras', o("pre-extras", "").split())
        createArgList('--post-extras', o("post-extras", "").split())
        createArgList('--products-initial', o("products-initial", "").split())
        createArgList('--products', o("products", "").split())
        createArgList('--profiles-initial', o("profiles-initial", "").split())
        createArgList('--profiles', o("profiles", "").split())

        return "%(scriptname)s %(args)s" % {
            "scriptname": self.get_internal_script("plonesite.py"),
            "args": " ".join(args)
            }


class Properties(Recipe):

    """
    This recipe writes all properties set on it into a .cfg in its part directory.
    It then runs a script to process this file and insert them into a plonesite as
    portal properties.
    """

    def get_command(self):
        location = os.path.join(self.buildout['buildout']['parts-directory'], self.name)
        if not os.path.isdir(location):
            os.makedirs(location)
        location = os.path.join(location, "properties.cfg")

        open(location, "w").write(self.options.get("properties", "{}"))
        self.installed.append(location)

        return "%(scriptname)s %(args)s" % {
            "scriptname": self.get_internal_script("setproperties.py"),
            "args": "--object=%s --properties=%s" % (self.options['object'], location)
            }


class Script(Recipe):

    """
    The script recipe takes a 'command' parameter: this is what to tell the
    instance script to run
    """

    def get_command(self):
        return self.options["command"]


class Wrapper(object):

    """
    The wrapper recipe generates scripts in bin/ for a list of entry points
    """
    parse_entry_point = re.compile(
        '([^=]+)=(\w+(?:[.]\w+)*):(\w+(?:[.]\w+)*)$'
        ).match


    def __init__(self, buildout, name, options):
        self.buildout = buildout
        self.name = name
        self.options = options

        self.options.setdefault("instance", "instance")
        self.options.setdefault("instance-script", os.path.join(buildout["buildout"]["bin-directory"], options["instance"]))
        self.options.setdefault("arguments", "app")

    def install(self):
        for s in self.options.get('entry-points', '').strip().split():
            parsed = self.parse_entry_point(s)
            if not parsed:
                raise UserError("Invalid entry-point: %s" % s)
            self.make_wrapper(*parsed.groups())

        return self.options.created()

    def make_wrapper(self, name, module, func):
        script = os.path.join(self.buildout['buildout']['bin-directory'], name)
        print "Generating wrapper: %s" % script

        f = open(script, "w")

        template = "#! %(instance_script)s run\n" + \
            "import %(module)s\n" + \
            "if __name__ == '__main__':\n" + \
            "    %(module)s.%(func)s(%(args)s)\n\n"

        f.write(template % {
            "instance_script": self.options['instance-script'],
            "module": module,
            "func": func,
            "args": self.options['arguments'],
            })
        f.close()

        os.chmod(script, 0755)

        self.options.created(script)

    def update(self):
        pass


