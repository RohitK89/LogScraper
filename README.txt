LogScraper
==========

A generic library for gathering stats from log files by running regexes
on them. Things you can do: \* Create and run any number of regexes on
any number of files in parallel. \* Aggregate stats by creating named
regex groups in your regexes \* Grab archived logs (so long as you tell
it where your archives live) \* Grab files from remote boxes \* Print
stats to console \* Print regex matches to console \* Search on gzipped
files

Installation
------------

The easiest manner of installation is to grab the package from the PyPI
repository.

::

    pip install log_scraper

Usage
-----

Base Usage
^^^^^^^^^^

For off the cuff usage, you can just create a LogScraper object and tell
it what regexes to run and where to look for files. Eg.

::

    from log_scraper.base import LogScraper
    import log_scraper.consts as LSC

    filepath = '/path/to/file'
    filename = 'filename.ext'
    scraper = LogScraper(default_filepath={LSC.DEFAULT_PATH : filepath, LSC.DEFAULT_FILENAME : filename})
    scraper.add_regex(name='regex1', pattern=r'your_regex_here')

    # To get aggregated stats
    data = scraper.get_log_data()

    # To print all the stats
    scraper.print_total_stats(data)

    # To print each file's individual stats
    scraper.print_stats_per_file(data)

    # To view log lines matching the regex
    scraper.view_regex_hits()

The real power, though, is in creating your own class deriving from
LogScraper that presets the paths and the regexes to run so that anyone
can then use that anywhere to mine data from a process' logs.

Development
-----------

Dependencies
~~~~~~~~~~~~

-  Python 2.7
-  `paramiko <http://paramiko-www.readthedocs.org/en/latest/index.html>`_

Testing
~~~~~~~

To test successfully, you must set up a virtual environment On Unix, in
the root folder for the package, do the following:
``python -m virtualenv . source ./bin/activate ./bin/python setup.py develop``

Now you can make any changes you want and then run the unit-tests by
doing:

::

    ./bin/python setup.py test
