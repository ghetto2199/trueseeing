import os
import sys

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.md')).read()
CHANGES = open(os.path.join(here, 'CHANGES.md')).read()

requires = []

setup(
  name='trueseeing',
  version='2.0.0',
  description='Trueseeing is Android vulnerability scanner and peneration test framework.',
  long_description=README + '\n\n' + CHANGES,
  classifiers=[
    "Programming Language :: Python",
    "Programming Language :: Java",
  ],
  author='Takahiro Yoshimura',
  author_email='altakey@gmail.com',
  url='https://github.com/taky/trueseeing',
  keywords='android java security pentest hacking',
  packages=find_packages(),
  package_data={'trueseeing':['libs/*.jar', 'libs/*.txt', 'libs/*.sql']},
  include_package_data=True,
  zip_safe=False,
  install_requires = requires,
  entry_points = {'console_scripts':['trueseeing = trueseeing.shell:entry']}
)
