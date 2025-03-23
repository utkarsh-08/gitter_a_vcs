from setuptools import setup

setup (name = 'gitter',
       version = '1.0.1',
       packages = ['gitter'],
       entry_points = {
           'console_scripts' : [
               'gitter = gitter.cli:main'
           ]
       })
