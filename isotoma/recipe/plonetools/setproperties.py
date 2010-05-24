"""
This script loads a file of properties stored in JSON format and sets then on a
plone site.

JSON takes care of making sure bools are bools and lists are lists so we don't
need to be too clever about introspection.
"""

import optparse, transaction
import simplejson as json

typemap = {
    "str": "string",
    "int": "int",
    "bool": "boolean",
    "list": "lines",
}

parser = optparse.OptionParser()
parser.add_option("-p", "--properties", dest="properties")
parser.add_option("-o", "--object", dest="object")
options, args = parser.parse_args()

# Support traversing from app down to a given object
portal = app
for k in options.object.split("."):
    poral = portal[k]

# Iterate over properties in properties.cfg and set them on the object
properties = json.loads(open(options.properties).read())
for key, value in properties.iteritems():
    # What kind of thing is this? We only support those in typemap
    typename = value.__class__.__name__
    if not typename in typemap.keys():
        print "Not setting %s, it has type %s" % (key, typename)
        continue
    typename = typemap[typename]

    print "Setting %s to '%s'" % (key, value)

    if not portal.hasProperty(key):
        portal.manage_addProperty(key, value, typename)
    else:
        portal.manage_changeProperties(**{key: value})

transaction.commit()
