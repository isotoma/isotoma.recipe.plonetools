import os
from datetime import datetime
from zope.app.component.hooks import setSite
import zc.buildout
import transaction
from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.SecurityManagement import noSecurityManager
from Testing import makerequest
from optparse import OptionParser
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

# the madness with the comma is a result of product names with spaces
def getProductsWithSpace(opts):
    return [x.replace(',', '') for x in opts]

def runProfiles(plone, profiles):
    print "Running profiles: %s" % profiles
    stool = plone.portal_setup
    for profile in profiles:
        if not profile.startswith('profile-'):
            profile = "profile-%s" % profile
        stool.runAllImportStepsFromProfile(profile)

def quickinstall(plone, products):
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

def create(app, site_id, products_initial, profiles_initial, site_replace):
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

def main(app, parser):
    (options, args) = parser.parse_args()
    site_id = options.site_id
    site_replace = options.site_replace
    admin_user = options.admin_user
    post_extras = options.post_extras
    pre_extras = options.pre_extras

    # normalize our product/profile lists
    products_initial = getProductsWithSpace(options.products_initial)
    products = getProductsWithSpace(options.products)
    profiles_initial = getProductsWithSpace(options.profiles_initial)
    profiles = getProductsWithSpace(options.profiles)

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
    # create the plone site if it doesn't exist
    create(app, site_id, products_initial, profiles_initial, site_replace)
    portal = getattr(app, site_id)
    # set the site so that the component architecture will work
    # properly
    setSite(portal)

    def runExtras(portal, script_path):
        if os.path.exists(script_path):
            execfile(script_path)
        else:
            msg = 'The path to the extras script does not exist: %s'
            raise zc.buildout.UserError(msg % script_path)

    for pre_extra in pre_extras:
        runExtras(portal, pre_extra)

    if products:
        quickinstall(portal, products)
    if profiles:
        runProfiles(portal, profiles)

    for post_extra in post_extras:
        runExtras(portal, post_extra)

    # commit the transaction
    transaction.commit()
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
    main(app, parser)
