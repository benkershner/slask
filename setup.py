#!/usr/bin/env python

from setuptools import setup

requires = ['flask>=0.0.0',
            'requests>=2.0.0']
            #'pyopenssl>=0.0.0']


setup(name='slask',
      version='0.1',
      description='A Flask app to republish to Slack',
      url='http://github.com/benkershner/slask',
      author='Ben Kershner',
      author_email='benkershner@gmail.com',
      license='MIT',
      packages=['slask'],
      install_requires=requires,
      scripts=['bin/slask'],
      zip_safe=False)
