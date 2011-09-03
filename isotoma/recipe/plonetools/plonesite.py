import os
from datetime import datetime
from zope.app.component.hooks import setSite
import zc.buildout
import transaction
from transaction.interfaces import TransientError
from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.SecurityManagement import noSecurityManager
from Testing import makerequest
from optparse import OptionParser

from Products.ZODBMountPoint.MountedObject import manage_addMounts
from Products.ZODBMountPoint.MountedObject import manage_getMountStatus

try:
    import json
except ImportError:
    import simplejson as json

try:
    from Products.PloneTestCase import version
except ImportError:
    version = None
pre_plone3 = False
try:
    from plone.app.linkintegrity.exceptions import \
        LinkIntegrityNotificationException
except ImportError:
    # we are using a release prior to 3.x
    pre_plone3 = True


class Plonesite(object):

    # the madness with the comma is a result of product names with spaces
    def getProductsWithSpace(self, opts):
        return [x.replace(',', '') for x in opts]

    def runProfiles(self, plone, profiles):
        print "Running profiles: %s" % profiles
        stool = plone.portal_setup
        for profile in profiles:
            if not profile.startswith('profile-'):
                profile = "profile-%s" % profile
            stool.runAllImportStepsFromProfile(profile)

    def quickinstall(self, plone, products):
        print "Quick installing: %s" % products
        qit = plone.portal_quickinstaller
        not_installed_ids = [
            x['id'] for x in qit.listInstallableProducts(skipInstalled=1)
        ]
        installed_ids = [x['id'] for x in qit.listInstalledProducts()]
        installed_products = filter(installed_ids.count, products)
        not_installed = filter(not_installed_ids.count, products)
        if installed_products:
            qit.reinstallProducts(installed_products)
        if not_installed_ids:
            qit.installProducts(not_installed)

    def create(self, app, site_id, products_initial, profiles_initial, site_replace):
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
                return
        # actually add in Plone
        if site_id not in oids:
            if version is not None and version.PLONE40:
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
            else:
                factory = app.manage_addProduct['CMFPlone']
                factory.addPloneSite(site_id, create_userfolder=1)
            # commit the new site to the database
            transaction.commit()
            print "Added Plone Site"

        # install some products
        plone = getattr(app, site_id)
        if plone:
            quickinstall(plone, products_initial)
        # run GS profiles
            runProfiles(plone, profiles_initial)
        print "Finished"

    def _retryable(self, error_type, error):
        if issubclass(error_type, TransientError):
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


    typemap = {
        "str": "string",
        "int": "int",
        "bool": "boolean",
        "list": "lines",
        }

    def set_properties(self, portal, path):
        # Iterate over properties in properties.cfg and set them on the object
        properties = json.load(open(path))
        for key, value in properties.iteritems():
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


    def set_mutators(self, portal, path):
        mutations = json.load(open(path))

        # Group all object updates together
        grouped = {}
        for mutator, value in mutations.iteritems():
            obj, setter = mutator.rsplit(".", 1)
            grouped.setdefault(obj, {})[setter] = value

        for obj, values in grouped.iteritems():
            parts = obj.split(".")
            target = portal
            while parts:
                target = getattr(target, parts.pop(0))

            for setter, value in values.iteritems():
                mutator = getattr(target, setter)
                mutator(value)


    @classmethod
    def main(cls, app, parser):
        (options, args) = parser.parse_args()

        p = cls()

        p.site_id = options.site_id
        p.site_replace = options.site_replace
        p.admin_user = options.admin_user
        p.post_extras = options.post_extras
        p.pre_extras = options.pre_extras

        # normalize our product/profile lists
        p.products_initial = getProductsWithSpace(options.products_initial)
        p.products = getProductsWithSpace(options.products)
        p.profiles_initial = getProductsWithSpace(options.profiles_initial)
        p.profiles = getProductsWithSpace(options.profiles)

        app = makerequest.makerequest(app)
        # set up security manager
        acl_users = app.acl_users
        user = acl_users.getUser(admin_user)
        if user:
            user = user.__of__(acl_users)
            newSecurityManager(None, user)
            print "Retrieved the admin user"
        else:
            raise zc.buildout.UserError('The admin-user specified does not exist')

        plonesite_parent = app

        if options.in_mountpoint:
            plonesite_parent = prepare_mountpoint(app, options.in_mountpoint)

        # create the plone site if it doesn't exist
        create(plonesite_parent, p.site_id, p.products_initial, p.profiles_initial, p.site_replace)
        portal = getattr(plonesite_parent, p.site_id)
        # set the site so that the component architecture will work
        # properly
        setSite(portal)

        def runExtras(portal, script_path):
            if os.path.exists(script_path):
                execfile(script_path)
            else:
                msg = 'The path to the extras script does not exist: %s'
                raise zc.buildout.UserError(msg % script_path)

        for pre_extra in p.pre_extras:
            runExtras(portal, pre_extra)

        if products:
            quickinstall(portal, p.products)
        if profiles:
            runProfiles(portal, p.profiles)

        if options.properties:
            set_properties(portal, options.properties)

        if options.mutators:
            set_mutators(portal, options.mutators)

        for post_extra in p.post_extras:
            runExtras(portal, post_extra)

        # commit the transaction
        transaction.commit(True)
        noSecurityManager()


if __name__ == '__main__':
    now_str = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    parser = OptionParser()
    parser.add_option("-s", "--site-id",
                      dest="site_id", default="Plone-%s" % now_str)
    parser.add_option("-r", "--site-replace",
                      dest="site_replace", action="store_true", default=False)
    parser.add_option("-u", "--admin-user",
                      dest="admin_user", default="admin")
    parser.add_option("-p", "--products-initial",
                      dest="products_initial", action="append", default=[])
    parser.add_option("-a", "--products",
                      dest="products", action="append", default=[])
    parser.add_option("-g", "--profiles-initial",
                      dest="profiles_initial", action="append", default=[])
    parser.add_option("-x", "--profiles",
                      dest="profiles", action="append", default=[])
    parser.add_option("-e", "--post-extras",
                      dest="post_extras", action="append", default=[])
    parser.add_option("-b", "--pre-extras",
                      dest="pre_extras", action="append", default=[])
    parser.add_option("-m", "--in-mount-point", default=None, dest="in_mountpoint")
    parser.add_option("--properties", action="store", dest="properties", default=None)
    parser.add_option("--mutators", action="store", dest="mutators", default=None)

    Plonesite.main(app, parser)
