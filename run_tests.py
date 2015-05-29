#!/usr/bin/env python

import os
import sys

import nose

def main(argv=None):
    if argv is None:
        argv = ['nosetests', '--cover-erase', '--with-coverage',
                '--cover-package=fds.log_scraper']

    nose.run_exit(argv=argv,
                  defaultTest=os.path.join(os.path.dirname(__file__), 'tests'))

if __name__ == '__main__':
    main(sys.argv)
