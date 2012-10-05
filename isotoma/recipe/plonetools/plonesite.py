import os, sys
from datetime import datetime
from zope.app.component.hooks import setSite
import zc.buildout
import transaction
from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.SecurityManagement import noSecurityManager
from Testing import makerequest
from optparse import OptionParser
import ConfigParser

from Products.CMFPlone.utils import getFSVersionTuple

from Products.ZODBMountPoint.MountedObject import manage_addMounts, \
    manage_getMountStatus, setMountPoint, MountedObject, CustomTrailblazer

from Products.SiteAccess.AccessRule import manage_addAccessRule, getAccessRule
from Products.SiteAccess.SiteRoot import manage_addSiteRoot

import tempfile
from App.config import getConfiguration


def migrate_mount_points(portal):
    # Based on a script by Andrew Mleczko
    # http://plone.org/documentation/kb/migrating-an-existing-catalog-in-a-new-zodb

    portal_path = portal.absolute_url_path() + "/"

    for mp in manage_getMountStatus(portal):
        if not mp['path'].startswith(portal_path):
            continue

        if not '** Something is in the way **' in mp['status']:
            continue

        print "Migrating '%s' to seperate ZODB storage" % mp['path']

        path = mp['path']
        id = path.split("/")[-1]

        # Existing objects
        old_obj = portal.unrestrictedTraverse(path)
        old_parent = old_obj.aq_parent.aq_base

        # New storage from the item
        db_name = mp['name']
        db = getConfiguration().dbtab.getDatabase(path)
        new_trans = db.open()

        # Try to get the root of the new storage
        root_dict = new_trans.root()
        if not root_dict.has_key('Application'):
            from OFS.Application import Application
            root_dict['Application'] = Application()
            transaction.savepoint(optimistic=True)

        # Verify there nothing in the way
        root = root_dict['Application']
        if id in root:
            print "  Cleaning target ZODB storage"
            root.manage_delObjects([id])

        print "  Exporting current state..."
        f = tempfile.TemporaryFile()
        old_obj._p_jar.exportFile(old_obj._p_oid, f)
        f.seek(0)

        print "  Importing into new external ZODB storage..."
        new_obj = root._p_jar.importFile(f)
        f.close()
        transaction.savepoint(optimistic=True)

        print "  Set the new object in the new storage..."
        blazer = CustomTrailblazer(root)
        obj = blazer.traverseOrConstruct(path)
        obj.aq_parent._setOb(id, new_obj)

        print "  Activating the new external storage..."
        mo = MountedObject(path)
        mo._create_mount_points = True

        old_parent._p_jar.add(mo)
        old_parent._setOb(id, mo)
        setMountPoint(old_parent, id, mo)

        transaction.savepoint(optimistic=True)

    transaction.commit()


try:
    import json
except ImportError:
    import simplejson as json

pre_plone3 = False
try:
    from plone.app.linkintegrity.exceptions import \
        LinkIntegrityNotificationException
except ImportError:
    # we are using a release prior to 3.x
    pre_plone3 = True

try:
    from transaction.interfaces import TransientError
except ImportError:
    TransientError = None

try:
    from ZODB.POSException import ConflictError
except ImportError:
    ConflictError = None

def has_factory_addPloneSite():
    try:
        from Products.CMFPlone.factory import addPloneSite
        addPloneSite  # please pyflakes
        return True
    except ImportError:
        return False


def deserialize(val):
    if "\n" in val:
        return val.strip().split("\n")
    elif val.lower in ("yes", "true", "on"):
        return True
    elif val.lower in ("no", "false", "off"):
        return False
    return val


class Plonesite(object):

    typemap = {
        "str": "string",
        "int": "int",
        "bool": "boolean",
        "list": "lines",
        }

    def __init__(self):
        self.site_id = 'Plone'
        self.site_replace = False
        self.admin_user = 'admin'
        self.attempts = 20

        self.post_extras = []
        self.pre_extras = []
        self.products_initial = []
        self.products = []
        self.profiles_initial = []
        self.profiles = []

        self.in_mountpoint = None
        self.rootify = False

        self.properties = {}
        self.mutators = {}

    # the madness with the comma is a result of product names with spaces
    def getProductsWithSpace(self, opts):
        return [x.replace(',', '') for x in opts]

    def runProfiles(self, plone, profiles):
        stool = plone.portal_setup
        for profile in profiles:
            if not profile.startswith('profile-'):
                profile = "profile-%s" % profile

            print "Running profile: %s" % profile
            if pre_plone3:
                stool.setImportContext(profile)
                stool.runAllImportSteps()
            else:
                stool.runAllImportStepsFromProfile(profile)

            transaction.savepoint()

    def quickinstall(self, plone, products):
        qit = plone.portal_quickinstaller
        not_installed_ids = [
            x['id'] for x in qit.listInstallableProducts(skipInstalled=1)
        ]
        installed_ids = [x['id'] for x in qit.listInstalledProducts()]
        installed_products = filter(installed_ids.count, products)
        not_installed = filter(not_installed_ids.count, products)
        if installed_products:
            for p in installed_products:
                print "Quick (re)installing %s" % p
                qit.reinstallProducts([p])
                transaction.savepoint()
        if not_installed_ids:
            for p in not_installed:
                print "Quick installing %s" % p
                qit.installProducts([p])
                transaction.savepoint()

    def create(self, app, site_id, site_replace):
        oids = app.objectIds()
        if site_id in oids:
            if site_replace and hasattr(app, site_id):
                if pre_plone3:
                    app.manage_delObjects([site_id,])
                else:
                    try:
                        app.manage_delObjects([site_id,])
                    except LinkIntegrityNotificationException:
                        pass
                transaction.commit()
                print "Removed existing Plone Site"
                oids = app.objectIds()
            else:
                print "A Plone Site already exists and will not be replaced"
                return False

        # actually add in Plone
        if site_id not in oids:
            version = getFSVersionTuple()
            if version[0] < 4:
                factory = app.manage_addProduct['CMFPlone']
                factory.addPloneSite(site_id, create_userfolder=1)

            else:
                # we have to simulate the new zmi admin screen here - at
                # least provide:
                # extension_ids
                # setup_content (plone default is currently 'true')
                from Products.CMFPlone.factory import addPloneSite
                extension_profiles = (
                    'plonetheme.classic:default',
                    'plonetheme.sunburst:default'
                    )
                addPloneSite(
                    app,
                    site_id,
                    extension_ids=extension_profiles,
                    setup_content=False
                    )

            # commit the new site to the database
            transaction.commit()
            print "Added Plone Site"

            return True

    def retryable(self, error_type, error):
        """
        I inspect an error and determient if it is transient and retryable or not

        If supported, I will ask all resources involved in the transaction if they
        think its a good idea to retry, by calling their ``should_retry`` method.
        """
        if TransientError and issubclass(error_type, TransientError):
            return True

        if ConflictError and issubclass(error_type, ConflictError):
            return True

        t = transaction.get()

        if not hasattr(t, "_resources"):
            return True

        for dm in transaction.get()._resources:
            should_retry = getattr(dm, 'should_retry', None)
            if (should_retry is not None) and should_retry(error):
                return True

    def prepare_mountpoint(self, app, path):
        for mountpoint in manage_getMountStatus(app):
            if mountpoint["path"] == path:
                break
        else:
            raise zc.buildout.UserError('That mountpoint does not exist in zope.conf')

        if mountpoint["status"] == "** Something is in the way **":
            raise zc.buildout.UserError("The current filestorage has an obstruction prevent use of the ZODB Mount '%s'!" % path)

        elif mountpoint["status"] == "Ready to create":
            manage_addMounts(app, (path, ))
            transaction.savepoint()
            print "Created mount point '%s'" % path

        elif mountpoint["status"] == "Ok":
            print "Mount point '%s' is Ok, nothing to update"

        else:
            raise zc.buildout.UserError("Mountpoint '%s' is '%s' - that is an unknown state, buildout cant continue" % (path, mountpoint["status"]))

        # Traverse from the root to wherever the mountpoint is, return that as the place the
        # plone site will be created
        retval = app
        for part in path.split("/"):
            if not part:
                continue
            retval = app[part]

        return retval


    def set_properties(self, portal, path):
        for key, value in self.properties.iteritems():
            # What kind of thing is this? We only support those in typemap
            typename = value.__class__.__name__
            if not typename in self.typemap.keys():
                print "Not setting %s, it has type %s" % (key, typename)
                continue
            typename = self.typemap[typename]
            print "Setting %s to '%s'" % (key, value)

            if not portal.hasProperty(key):
                portal.manage_addProperty(key, value, typename)
            else:
                portal.manage_changeProperties(**{key: value})

        transaction.savepoint()


    def set_mutators(self, portal, path):
        grouped = {}
        for mutator, value in self.mutators.iteritems():
            obj, setter = mutator.rsplit(".", 1)
            grouped.setdefault(obj, {})[setter] = value

        for obj, values in grouped.iteritems():
            print "Setting values on %s" % obj
            parts = obj.split(".")
            target = portal
            while parts:
                target = target[parts.pop(0)]

            for setter, value in values.iteritems():
                print "  %s = %s" % (setter, value)
                mutator = getattr(target, setter)
                mutator(value)

        transaction.savepoint()

    def rootify_site(self, app, portal):
        print "Ensuring site is visible at '/'"

        if not "rootify" in app.objectIds():
            print "    Adding DTMLMethod 'rootify'..."
            app.addDTMLMethod('rootify', file="""
              <dtml-let stack="REQUEST['TraversalRequestNameStack']">
                <dtml-if "stack and stack[-1]=='zmi'">
                  <dtml-call "stack.pop()">
                  <dtml-call "REQUEST.setVirtualRoot('zmi')">
                <dtml-else>
                  <dtml-call "stack.append('%s')">
                </dtml-if>
              </dtml-let>
              """ % portal.getId())
        else:
            print "    Skipped adding DTMLMethod."

        if getAccessRule(app) != "rootify":
            print "    Adding AccessRule..."
            manage_addAccessRule(app, "rootify")
        else:
            print "    Skipped adding AccessRule."

        if not "SiteRoot" in portal.objectIds():
            print "    Adding SiteRoot..."
            manage_addSiteRoot(portal, title="SiteRoot", base="", path="/")
        else:
            print "    Skipped adding SiteRoot."

        transaction.savepoint()

    def run(self, app):
        app = makerequest.makerequest(app)

        try:
            from zope.globalrequest import setRequest
            # support plone.subrequest
            app.REQUEST['PARENTS'] = [app]
            setRequest(app.REQUEST)
        except ImportError:
            pass

        # set up security manager
        acl_users = app.acl_users
        user = acl_users.getUser(self.admin_user)
        if user:
            user = user.__of__(acl_users)
            newSecurityManager(None, user)
            print "Retrieved the admin user"
        else:
            raise zc.buildout.UserError('The admin-user specified does not exist')

        plonesite_parent = app

        if self.in_mountpoint:
            plonesite_parent = prepare_mountpoint(app, self.in_mountpoint)

        # create the plone site if it doesn't exist
        created_new_site = self.create(plonesite_parent, self.site_id, self.site_replace)
        portal = getattr(plonesite_parent, self.site_id)

        # set the site so that the component architecture will work
        # properly
        if not pre_plone3:
            setSite(portal)

        migrate_mount_points(portal)

        if created_new_site:
            self.quickinstall(portal, self.products_initial)
            # run GS profiles
            self.runProfiles(portal, self.profiles_initial)

        def runExtras(portal, script_path):
            if not os.path.exists(script_path):
                msg = 'The path to the extras script does not exist: %s'
                raise zc.buildout.UserError(msg % script_path)
            print "Running extra:", script_path
            execfile(script_path, {"app": app, "portal": portal})

        for pre_extra in self.pre_extras:
            runExtras(portal, pre_extra)

        if self.products:
            self.quickinstall(portal, self.products)

        if self.profiles:
            self.runProfiles(portal, self.profiles)

        if self.properties:
            self.set_properties(portal, self.properties)

        if self.mutators:
            self.set_mutators(portal, self.mutators)

        if self.rootify:
            self.rootify_site(app, portal)

        for post_extra in self.post_extras:
            runExtras(portal, post_extra)

        # commit the transaction
        transaction.commit()
        noSecurityManager()

        print "Finished"

    def configure_from_file(self, path):
        cfg = ConfigParser.RawConfigParser()
        cfg.optionxform = str

        cfg.read(path)

        if cfg.has_option("main", "site-id"):
            self.site_id = cfg.get("main", "site-id")
        else:
            self.site_id = "Plone"

        if cfg.has_option("main", "site-replace"):
            self.site_replace = cfg.getboolean("main", "site-replace")
        else:
            self.site_replace = False

        if cfg.has_option("main", "admin-user"):
            self.admin_user = cfg.get("main", "admin-user")
        else:
            self.admin_user = "admin"

        if cfg.has_option("main", "post-extras"):
            self.post_extras = cfg.get("main", "post-extras").strip().split()
        if cfg.has_option("main", "pre-extras"):
            self.pre_extras = cfg.get("main", "pre-extras").strip().split()

        # normalize our product/profile lists
        if cfg.has_option("main", "products-initial"):
            self.products_initial = self.getProductsWithSpace(cfg.get("main", "products-initial").strip().split())
        if cfg.has_option("main", "products"):
            self.products = self.getProductsWithSpace(cfg.get("main", "products").strip().split())
        if cfg.has_option("main", "profiles-initial"):
            self.profiles_initial = self.getProductsWithSpace(cfg.get("main", "profiles-initial").strip().split())
        if cfg.has_option("main", "profiles"):
            self.profiles = self.getProductsWithSpace(cfg.get("main", "profiles").strip().split())

        if cfg.has_option("main", "in_mountpoint"):
            self.in_mountpoint = options.in_mountpoint

        if cfg.has_option("main", "rootify") and cfg.getboolean("main", "rootify"):
            self.rootify = True
        else:
            self.rootify = False

        if cfg.has_section("properties"):
            for k, v in cfg.items("properties"):
                self.properties[k] = deserialize(v)

        if cfg.has_section("mutators"):
            for k, v in cfg.items("mutators"):
                self.mutators[k] = deserialize(v)

        if cfg.has_option("main", "attempts"):
            self.attempts = cfg.getint("main", "attempts")

    @classmethod
    def main(cls, app, config=None):
        parser = OptionParser()
        parser.add_option("-c", "--config", default=config)
        parser.add_option("-r", "--replace", action="store_true")
        options, args = parser.parse_args()

        p = cls()
        p.configure_from_file(options.config)
        p.site_replace = options.replace

        for i in range(int(p.attempts)):
            try:
                p.run(app)
            except:
                (type, value, traceback) = sys.exc_info()

                if not p.retryable(type, value):
                    raise
                print "A recoverable TransientError was handled, retrying..."
                transaction.abort()
            else:
                break

        # Make sure worker threads are killed off
        try:
            from Products.CMFSquidTool.utils import stopThreads
            print "Stopping CMFSquidTool purge queue..."
            stopThreads()

        except ImportError:
            # Import error means no CacheSetup; so dont worry
            pass

if __name__ == '__main__':
    Plonesite.main(app)

