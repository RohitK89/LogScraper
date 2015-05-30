from setuptools import setup, find_packages

with open('README.txt') as file:
    long_description = file.read()

setup(
    name                ='log_scraper',
    version             ='0.9.4',
    install_requires    =['paramiko'],
    package_dir         ={'': 'src'},
    packages            =find_packages('src'),
    namespace_packages  =['log_scraper'],

    # metadata for upload to PyPI
    author              ='Rohit Kapur',
    author_email        ='rohitkapur@rohitkapur.com',
    maintainer          ='Rohit Kapur',
    maintainer_email    ='rohitkapur@rohitkapur.com',
    description         =(
                'A base library for writing your own log scraper, '
                'i.e. something that can run regexes over files '
                'and give you meaningful information like stats. '
                'Add your own regexes and plug and play. '
                'See the readme for more information.'
    ),
    long_description    = long_description,
    license             ='Simplified BSD License',
    platforms           =['UNIX', 'OS X', 'Windows'],
    url                 ='https://github.com/RohitK89/LogScraper/',
    download_url        ='https://github.com/RohitK89/LogScraper/tarball/0.9.4',
    keywords            =['log scraper','logs','regex','stats','grep'],
    test_suite          ='run_tests.main',
    tests_require       =['coverage', 'nose']
)
