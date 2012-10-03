from setuptools import setup, find_packages

version = '0.0.15.dev0'

setup(
    name = 'isotoma.recipe.plonetools',
    version = version,
    description = "Buildout recipes for setting up a plone site.",
    url = "http://pypi.python.org/pypi/isotoma.recipe.plonetools",
    long_description = open("README.rst").read() + "\n" + \
                       open("CHANGES.txt").read(),
    classifiers = [
        "Framework :: Buildout",
        "Intended Audience :: System Administrators",
        "Operating System :: POSIX",
        "License :: OSI Approved :: Zope Public License",
    ],
    keywords = "buildout plone",
    author = "John Carr",
    author_email = "john.carr@isotoma.com",
    license="Apache Software License",
    packages = find_packages(exclude=['ez_setup']),
    package_data = {
        '': ['README.rst', 'CHANGES.txt'],
    },
    namespace_packages = ['isotoma', 'isotoma.recipe'],
    include_package_data = True,
    zip_safe = False,
    install_requires = [
        'setuptools',
        'zc.buildout',
    ],
    entry_points = {
        "zc.buildout": [
            "default = isotoma.recipe.plonetools:Site",
            "site = isotoma.recipe.plonetools:Site",
            "wrapper = isotoma.recipe.plonetools:Wrapper",
        ],
    }
)
