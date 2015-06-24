'''
Unit-tests for the Log Scraper library
'''

from collections import OrderedDict
from datetime import datetime, timedelta
from StringIO import StringIO
import gzip
import os
import shutil
import socket
import sys
import unittest

BASE_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.append(BASE_PATH)

from src.log_scraper.base import LogScraper, RegexObject
from src.log_scraper.base import BadRegexException, MissingArgumentException, InvalidArgumentException
import src.log_scraper.consts as LSC

#DIRS
ARCHIVE_DIR = 'archived'
LOG_DIR = './logs'
LOG_FILE = 'log*.log'
LOG_FILE_REGEX = r'log\d+'

#Log files
LOG_FILE_1 = ("log1.log",
'''My name is Judge.
My name is Franklin.
Judge my name?
My name is Judge.
'''
             )
LOG_FILE_2 = ("log2.log",
'''The weather is sunny.
The time is noon.
My name is Judge.
What's my name?
My name is Franklin.
The weather is rainy.
The weather is icy.
'''
             )
# Remote coyping needs full path
REMOTE_LOG_FILE_PATH = os.path.join(BASE_PATH, 'logs', LOG_FILE_1[0])
REMOTE_FILE_1 = 'log1-this_box.log'
REMOTE_FILE_2 = 'log2-this_box.log'
TMP_REMOTE_DIR = './tmp_remote'

def _clean_dir(xdir=LOG_DIR):
    '''Set up directory structure. Will delete any existing directories and files.'''
    if os.path.exists(xdir):
        shutil.rmtree(xdir)
    os.makedirs(xdir)
    os.mkdir(os.path.join(xdir, ARCHIVE_DIR))

def _write_file(filename, contents, inc_dir=LOG_DIR):
    '''
    Takes a filename, contents and path and writes out file
    '''
    with open(os.path.join(inc_dir, filename), 'w') as mfile:
        mfile.write(contents)

def _write_file_from_pair(filename, inc_dir=LOG_DIR):
    '''
    Takes a tuple that has as its first element a filename, and the second as the contents,
    and writes out the file to the path provided in the inc_dir param.
    '''
    with open(os.path.join(inc_dir, filename[0]), 'w') as mfile:
        mfile.write(filename[1])

class LogScraperWithOptions(LogScraper):
    '''A sample implementation of the log scraper library that sets some of the optional params'''

    def __init__(self, user_params):
        default_filepath = {}
        optional_params = {}

        default_filepath[LSC.DEFAULT_PATH] = LOG_DIR
        default_filepath[LSC.DEFAULT_FILENAME] = LOG_FILE
        optional_params[LSC.DAYS_BEFORE_ARCHIVING] = 1
        optional_params[LSC.LEVELS_TO_BOXES] = {'this_box' : socket.gethostname()}

        super(LogScraperWithOptions, self).__init__(default_filepath=default_filepath,
                                                    optional_params=optional_params,
                                                    user_params=user_params)

    def _init_regexes(self):
        '''Sample regexes'''
        no_group_regex = r'My name is Judge\.$'
        group_regex = r'My name is (?P<name>\w+)\.$'
        self._regexes.append(RegexObject(name='no_group', pattern=no_group_regex))
        self._regexes.append(RegexObject(name='group', pattern=group_regex))

    def _get_archived_file_path(self):
        '''Where logs are archived'''
        return os.path.join(LOG_DIR, ARCHIVE_DIR)

class TestLogScraper(unittest.TestCase):
    '''Creates a simple log scraper and tests out all the functionality'''

    def setUp(self):
        '''Create the log scraper to use, write out the test log files'''
        #Write out the sample log files
        _clean_dir()
        _write_file_from_pair(LOG_FILE_1)
        _write_file_from_pair(LOG_FILE_2)
        _write_file_from_pair((LOG_FILE_1[0].split('.')[0] + '-20150301.log', LOG_FILE_1[1]),
                              os.path.join(LOG_DIR, ARCHIVE_DIR))
        _write_file_from_pair((LOG_FILE_2[0].split('.')[0] + '-20150301.log', LOG_FILE_2[1]),
                              os.path.join(LOG_DIR, ARCHIVE_DIR))

    def test_setting_user_params(self):
        '''Tests to make sure that the user params dict is set correctly'''
        _log_scraper = LogScraper()
        self.assertEquals(_log_scraper.get_user_params(), {})

        user_params = {'TEST' : 'TEST1'}

        _log_scraper.set_user_params(user_params)
        self.assertEquals(_log_scraper.get_user_params(), user_params)

    def test_base_scraper(self):
        '''Test the no-nonsense simple scraper'''

        _log_scraper = LogScraper()
        expected = ("LogScraper(default_filename=, default_filepath=, "
                    "optional_params={'levels_to_boxes': {}, 'filename_regex': '', "
                    "'processor_count': 4, 'local_copy_lifetime': 0, 'tmp_path': '', "
                    "'force_copy': False, 'days_before_archiving': 0}, user_params={}")
        self.assertEquals(repr(_log_scraper), expected)

        expected = ("Regexes: []\n"
                    "Default filename: \n"
                    "Default filepath: \n"
                    "Optional params: {'levels_to_boxes': {}, 'filename_regex': '', "
                    "'processor_count': 4, 'local_copy_lifetime': 0, 'tmp_path': '', "
                    "'force_copy': False, 'days_before_archiving': 0}\n"
                    "User params: {}")
        self.assertEquals(str(_log_scraper), expected)

        #Set file list
        user_params = {}
        user_params[LSC.DEBUG] = True
        user_params[LSC.FILENAME] = os.path.join(LOG_DIR, LOG_FILE)
        _log_scraper.set_user_params(user_params)

        #Add some regexes
        no_group_regex = r'My name is Judge\.$'
        group_regex = r'The (?P<key>\w+) is (?P<value>\w+)\.$'
        _log_scraper.add_regex(name='name_is_judge', pattern=no_group_regex)
        _log_scraper.add_regex(name='key_value_regex', pattern=group_regex)

        # Validate user params (should do nothing)
        _log_scraper._validate_user_params()
        
        # Should give back nothing
        self.assertEquals(_log_scraper._get_archived_file_path(), None)

        #Finally, get some data
        results = _log_scraper.get_log_data()

        expected = {'regexes' : {'key_value_regex': {'group_hits': {'key': OrderedDict([('time', 1),
                                                                                       ('weather', 3)]),
                                                                    'value': OrderedDict([('icy', 1),
                                                                                          ('noon', 1),
                                                                                          ('rainy', 1),
                                                                                          ('sunny', 1)])},
                                                     'total_hits': 4},
                                 'name_is_judge': {'group_hits': {}, 'total_hits': 3}},
                    'file_hits': [{'regexes': {'key_value_regex': {'group_hits': {'value': OrderedDict(),
                                                                                  'key': OrderedDict()},
                                                                   'total_hits': 0},
                                               'name_is_judge': {'group_hits': {}, 'total_hits': 2}},
                                   'filename': './logs/log1.log'},
                                  {'regexes': {'key_value_regex': {'group_hits': {'value': OrderedDict([('icy', 1),
                                                                                                        ('noon', 1),
                                                                                                        ('rainy', 1),
                                                                                                        ('sunny', 1)]),
                                                                                  'key': OrderedDict([('time', 1),
                                                                                                      ('weather', 3)])},
                                                                   'total_hits': 4},
                                               'name_is_judge': {'group_hits': {},
                                                                 'total_hits': 1}},
                                   'filename': './logs/log2.log'}]}

        self.maxDiff = None
        self.assertDictEqual(results, expected)

        # Test the min/max/avg
        # Test with no data
        stats = _log_scraper._calc_stats([])
        expected = {'max_key': 0,
                    'max_count': 0,
                    'avg_count': 0,
                    'min_count': 0,
                    'min_key': 0}
        self.assertDictEqual(stats, expected)

        stats = _log_scraper._calc_stats(results['regexes']['key_value_regex'][LSC.GROUP_HITS]['key'])
        expected = {'max_key': 'weather',
                    'max_count': 3,
                    'avg_count': 2.0,
                    'min_count': 1,
                    'min_key': 'time'}
        self.assertDictEqual(stats, expected)

        # Test viewing regex hits
        matches = _log_scraper.get_regex_matches()
        self.assertEquals(len(matches), 2)
        self.assertEquals(matches[0][LSC.FILENAME], os.path.join(LOG_DIR, LOG_FILE_1[0]))
        self.assertEquals(len(matches[0][LSC.REGEXES]['key_value_regex'][LSC.MATCHES]), 0)
        self.assertEquals(len(matches[0][LSC.REGEXES]['name_is_judge'][LSC.MATCHES]), 2)
        self.assertEquals(matches[1][LSC.FILENAME], os.path.join(LOG_DIR, LOG_FILE_2[0]))
        self.assertEquals(len(matches[1][LSC.REGEXES]['key_value_regex'][LSC.MATCHES]), 4)
        self.assertEquals(len(matches[1][LSC.REGEXES]['name_is_judge'][LSC.MATCHES]), 1)

    def test_no_match_regex(self):
        '''How regexes that don't match anything are handled'''

        _log_scraper = LogScraper()

        #Set file list
        user_params = {}
        user_params[LSC.FILENAME] = os.path.join(LOG_DIR, LOG_FILE)
        _log_scraper.set_user_params(user_params)

        #Add some regexes
        no_group_regex = r'This should not match\.$'
        _log_scraper.add_regex(name='no_match', pattern=no_group_regex)

        results = _log_scraper.get_log_data()
        self.assertEquals(results[LSC.REGEXES]['no_match'][LSC.TOTAL_HITS], 0)

    def test_archived_scraping(self):
        '''Test the scraper that fetches archived files'''

        user_params = {}
        user_params[LSC.DATE] = '20150301'
        user_params[LSC.DEBUG] = True
        _option_scraper = LogScraperWithOptions(user_params=user_params)

        results = _option_scraper.get_log_data()
        expected = {'regexes' : {'no_group': {'group_hits': {}, 'total_hits': 3},
                                 'group': {'group_hits': {'name': OrderedDict([('Franklin', 2), ('Judge', 3)])},
                                           'total_hits': 5}},
                    'file_hits': [{'regexes': {'no_group': {'group_hits': {},
                                                            'total_hits': 2},
                                               'group': {'group_hits': {'name': OrderedDict([('Franklin', 1),
                                                                                             ('Judge', 2)])},
                                                         'total_hits': 3}},
                                   'filename': './logs/archived/log1-20150301.log'},
                                  {'regexes': {'no_group': {'group_hits': {},
                                                            'total_hits': 1},
                                               'group': {'group_hits': {'name': OrderedDict([('Franklin', 1),
                                                                                             ('Judge', 1)])},
                                                         'total_hits': 2}},
                                   'filename': './logs/archived/log2-20150301.log'}]}
        self.assertDictEqual(results, expected)

        test_date = datetime.today().strftime('%Y%m%d')
        # Yes, yes, it's testing a private method directly. Let's move on
        self.assertFalse(_option_scraper._are_logs_archived(test_date))

    def test_regexes(self):
        '''Test the logic for adding and removing regexes from the scraper'''
        _log_scraper = LogScraper()

        pattern = 'Very Specific Regex'
        regex_obj = RegexObject(name='test_regex', pattern=pattern)
        self.assertEqual(regex_obj.get_pattern(), pattern)
        matcher = regex_obj.get_matcher()
        self.assertEqual(matcher.match(pattern).group(), pattern)

        new_pattern = 'New (?P<group>(Pattern))'
        regex_obj.update_pattern(new_pattern)
        self.assertEqual(regex_obj.get_pattern(), new_pattern)
        matcher = regex_obj.get_matcher()
        self.assertEqual(regex_obj.__repr__(),
                         'RegexObject(name=test_regex, pattern=New (?P<group>(Pattern)))')

        self.assertEqual(regex_obj.__str__(),
                         "Pattern: New (?P<group>(Pattern)), Groups: ['group']")

        self.assertEqual(regex_obj.get_groups(), ['group'])


        _log_scraper.add_regex(name='test_regex', pattern='.*')

        self.assertEqual(1, len(_log_scraper.get_regexes()))

        _log_scraper.add_regex(name='test_regex_2', pattern='^.*$')

        self.assertEqual(2, len(_log_scraper.get_regexes()))

        # Clear regexes and test size
        _log_scraper.clear_regexes()

        self.assertEqual(0, len(_log_scraper.get_regexes()))

        # Give a bad pattern
        with self.assertRaises(BadRegexException):
            _log_scraper.add_regex(name='bad_regex', pattern='?P<whoops')

    def test_remote_file_copying(self):
        '''Tests to see if it copies file over SSH properly'''

        if os.path.exists(TMP_REMOTE_DIR):
            shutil.rmtree(TMP_REMOTE_DIR)
        os.makedirs(TMP_REMOTE_DIR)
        _write_file(REMOTE_FILE_1, LOG_FILE_1[1])
        _write_file(REMOTE_FILE_2, LOG_FILE_2[1])

        default_filepath = {}
        default_filepath[LSC.DEFAULT_PATH] = os.path.join(BASE_PATH, 'logs')
        default_filepath[LSC.DEFAULT_FILENAME] = LOG_FILE

        user_params = {LSC.LEVEL : 'this_box',
                       LSC.FILENAME : REMOTE_LOG_FILE_PATH}
        user_params[LSC.DEBUG] = True

        # Test SSHing with correct values
        optional_params = {LSC.TMP_PATH : TMP_REMOTE_DIR,
                           LSC.LOCAL_COPY_LIFETIME : 1,
                           LSC.LEVELS_TO_BOXES : {'this_box' : socket.gethostname()},
                           LSC.FILENAME_REGEX : LOG_FILE_REGEX,
                           LSC.FORCE_COPY : True}

        _log_scraper = LogScraper(default_filepath=default_filepath,
                                  user_params=user_params,
                                  optional_params=optional_params)

        file_list = _log_scraper._get_file_list()
        for scraper_file in file_list:
            _log_scraper._get_log_file(scraper_file)

        expected_files = []
        for filename in [REMOTE_FILE_1, REMOTE_FILE_2]:
            tmp_file = os.path.join(TMP_REMOTE_DIR, '_'.join(['this_box', filename]))
            self.assertTrue(os.path.exists(tmp_file))
            expected_files.append(tmp_file)

        # Store the modification time of the locally copied file.
        # We're going to repeat the copy operation, and since the file is new,
        # there should be no recopying
        mtimes = []
        for filepath in expected_files:
            mtimes.append(os.path.getmtime(filepath))

        copied_files = []
        for scraper_file in file_list:
            copied_files.append(_log_scraper._get_log_file(scraper_file))

        self.assertEquals(expected_files, copied_files)

        # Compare mtimes
        copied_mtimes = []
        for filepath in copied_files:
            copied_mtimes.append(os.path.getmtime(filepath))

        self.assertEquals(mtimes, copied_mtimes)

        # Test copying remote files when local copy is out of date
        optional_params[LSC.LOCAL_COPY_LIFETIME] = 0
        _log_scraper = LogScraper(default_filepath=default_filepath,
                                  user_params=user_params,
                                  optional_params=optional_params)

        file_list = _log_scraper._get_file_list()
        copied_files = []
        for scraper_file in file_list:
            copied_files.append(_log_scraper._get_log_file(scraper_file))

        self.assertEquals(expected_files, copied_files)

        # Compare mtimes
        copied_mtimes = []
        for filepath in copied_files:
            copied_mtimes.append(os.path.getmtime(filepath))

        self.assertNotEqual(mtimes, copied_mtimes)

        # Test SSHing with bad box name
        optional_params = {LSC.TMP_PATH : TMP_REMOTE_DIR,
                           LSC.LOCAL_COPY_LIFETIME : 1,
                           LSC.LEVELS_TO_BOXES : {'this_box' : 'bad_box'},
                           LSC.FILENAME_REGEX : LOG_FILE_REGEX,
                           LSC.FORCE_COPY : True}

        _log_scraper = LogScraper(default_filepath=default_filepath,
                                  user_params=user_params,
                                  optional_params=optional_params)

        self.assertEquals(_log_scraper.get_log_data(), None)
        for filename in [REMOTE_FILE_1, REMOTE_FILE_2]:
            tmp_file = os.path.join(TMP_REMOTE_DIR, '_'.join(['bad_box', filename]))
            self.assertFalse(os.path.exists(tmp_file))

        shutil.rmtree(TMP_REMOTE_DIR)

    def test_file_path_creation(self):
        '''Run the file path creation logic through its paces'''

        # No default paths, so no path should be made
        _log_scraper = LogScraper()
        self.assertEquals(_log_scraper._make_file_path(), '')

        # Test with default filepath
        default_filepath = {}
        default_filepath[LSC.DEFAULT_PATH] = os.path.join(BASE_PATH, 'logs')
        default_filepath[LSC.DEFAULT_FILENAME] = LOG_FILE
        _log_scraper = LogScraper(default_filepath=default_filepath)
        log_file_parts = LOG_FILE.split('.')
        expected = os.path.join(BASE_PATH, 'logs', LOG_FILE)
        self.assertEquals(_log_scraper._make_file_path(), expected)

        # Test with date and non-archival
        user_params = {}
        test_date = datetime.today().strftime('%Y%m%d')
        user_params[LSC.DATE] = test_date
        _option_scraper = LogScraperWithOptions(user_params=user_params)
        expected = os.path.join(LOG_DIR,
                                '.'.join(['-'.join([log_file_parts[0], test_date]),
                                          log_file_parts[1]]))
        self.assertEquals(_option_scraper._make_file_path(), expected)

        # Non-archival with box name and no date
        user_params = {LSC.LEVEL : 'this_box'}

        optional_params = {LSC.LEVELS_TO_BOXES : {'this_box' : socket.gethostname()},
                           LSC.FILENAME_REGEX : LOG_FILE_REGEX}
        _log_scraper = LogScraper(default_filepath=default_filepath,
                                  optional_params=optional_params,
                                  user_params=user_params)
        expected = os.path.join(BASE_PATH, 'logs',
                                '.'.join(['-'.join([log_file_parts[0], socket.gethostname()]),
                                          log_file_parts[1]]))
        self.assertEquals(_log_scraper._make_file_path(), expected)

        # Non-archival with box name and date
        user_params = {LSC.LEVEL : 'this_box',
                       LSC.DATE : test_date}

        optional_params = {LSC.LEVELS_TO_BOXES : {'this_box' : socket.gethostname()},
                           LSC.FILENAME_REGEX : LOG_FILE_REGEX}
        _log_scraper = LogScraper(default_filepath=default_filepath,
                                  optional_params=optional_params,
                                  user_params=user_params)
        expected = os.path.join(BASE_PATH, 'logs',
                                '.'.join(['-'.join([log_file_parts[0], socket.gethostname(),
                                                    test_date]),
                                          log_file_parts[1]]))
        self.assertEquals(_log_scraper._make_file_path(), expected)

        # Archival with box name and date
        test_date = datetime.today() - timedelta(2)
        test_date = test_date.strftime('%Y%m%d')
        user_params = {LSC.LEVEL : 'this_box',
                       LSC.DATE : test_date}

        _option_scraper = LogScraperWithOptions(user_params=user_params)
        expected = os.path.join(LOG_DIR, ARCHIVE_DIR,
                                '.'.join(['-'.join([log_file_parts[0], socket.gethostname(),
                                                    test_date]),
                                          log_file_parts[1] + '*']))
        self.assertEquals(_option_scraper._make_file_path(), expected)


    def test_bad_filepath(self):
        '''Create a log scraper with a bad filepath'''

        _log_scraper = LogScraper()

        #Should return None as no files should be found
        self.assertEqual(_log_scraper.get_log_data(), None)

        user_params = {}
        user_params[LSC.FILENAME] = '/this/path/does/not/exist/'
        user_params[LSC.DEBUG] = True
        _log_scraper.set_user_params(user_params)
        #Should return None as no files should be found
        self.assertEqual(_log_scraper.get_log_data(), None)
        self.assertEqual(_log_scraper.get_regex_matches(), None)

    def test_good_filepath(self):
        '''Create a log scraper with a good filepath'''
        user_params = {}
        user_params[LSC.FILENAME] = os.path.join(LOG_DIR, LOG_FILE)
        user_params[LSC.DEBUG] = True
        _option_scraper = LogScraperWithOptions(user_params=user_params)

        results = _option_scraper.get_log_data()
        expected = {'regexes' : {'no_group': {'group_hits': {}, 'total_hits': 3},
                                 'group': {'group_hits': {'name': OrderedDict([('Franklin', 2),
                                                                               ('Judge', 3)])},
                                           'total_hits': 5}},
                    'file_hits': [{'regexes': {'no_group': {'group_hits': {},
                                                            'total_hits': 2},
                                               'group': {'group_hits': {'name': OrderedDict([('Franklin', 1),
                                                                                             ('Judge', 2)])},
                                                         'total_hits': 3}},
                                   'filename': './logs/log1.log'},
                                  {'regexes': {'no_group': {'group_hits': {},
                                                            'total_hits': 1},
                                               'group': {'group_hits': {'name': OrderedDict([('Franklin', 1),
                                                                                             ('Judge', 1)])},
                                               'total_hits': 2}},
                                   'filename': './logs/log2.log'}]}
        self.assertDictEqual(results, expected)


    def test_printing(self):
        '''Test the functions that print stuff out'''
        _log_scraper = LogScraper()
        out = StringIO()
        _log_scraper.print_total_stats(None, out=out)
        self.assertEquals(out.getvalue(), '')

        _log_scraper.print_stats_per_file(None, out=out)
        self.assertEquals(out.getvalue(), '')

        #Set file list
        user_params = {}
        user_params[LSC.FILENAME] = os.path.join(LOG_DIR, LOG_FILE)
        _log_scraper.set_user_params(user_params)

        #Add some regexes
        no_group_regex = r'My name is Judge\.$'
        _log_scraper.add_regex(name='name_is_judge', pattern=no_group_regex)

        # Test printing without debug mode
        results = _log_scraper.get_log_data()
        _log_scraper.print_total_stats(results, out=out)
        expected = '\x1b[94m\x1b[0m\x1b[92mTotal hits for regex Name_is_judge: 3\n\x1b[0m'
        self.assertEquals(out.getvalue(), expected)

        out.close()
        out = StringIO()

        _log_scraper.print_stats_per_file(results, out=out)
        expected = 'File: ./logs/log1.log\n\x1b[94m\x1b[0mFile: ./logs/log2.log\n\x1b[94m\x1b[0m'
        self.assertEquals(out.getvalue(), expected)

        # Test printing with debug mode
        out.close()
        out = StringIO()

        user_params[LSC.DEBUG] = True
        _log_scraper.set_user_params(user_params)

        results = _log_scraper.get_log_data()
        _log_scraper.print_total_stats(results, out=out)
        expected = ('\x1b[94m\nTotal Name_is_judge hits: 3\n\x1b[0m\x1b[92m'
                    'Total hits for regex Name_is_judge: 3\n\x1b[0m')
        self.assertEquals(out.getvalue(), expected)

        out.close()
        out = StringIO()

        _log_scraper.print_stats_per_file(results, out=out)
        expected = ('File: ./logs/log1.log\n\x1b[94m\n'
                    'Total Name_is_judge hits: 2\n\x1b[0m'
                    'File: ./logs/log2.log\n\x1b[94m\n'
                    'Total Name_is_judge hits: 1\n\x1b[0m')
        self.assertEquals(out.getvalue(), expected)

        # Test printing regex matches
        _log_scraper.add_regex(name='no_match', pattern='No match')
        results = _log_scraper.get_regex_matches()
        out.close()
        out = StringIO()
        expected = ('Regex: no_match\n'
                    'Matches:\n'
                    './logs/log1.log-No matches\n'
                    'Regex: name_is_judge\n'
                    'Matches:\n'
                    './logs/log1.log-My name is Judge.\n'
                    './logs/log1.log-My name is Judge.\n'
                    'Regex: no_match\n'
                    'Matches:\n'
                    './logs/log2.log-No matches\n'
                    'Regex: name_is_judge\n'
                    'Matches:\n'
                    './logs/log2.log-My name is Judge.\n')
        _log_scraper.view_regex_matches(out=out)
        self.assertEquals(out.getvalue(), expected)

    def test_file_reading(self):
        '''Test the opening and reading of files'''

        _log_scraper = LogScraperWithOptions({})
        # Test regular files
        contents = LOG_FILE_1[1].splitlines(True)
        cntr = 0
        for line in _log_scraper._gen_lines(os.path.join(LOG_DIR, LOG_FILE_1[0])):
            self.assertEquals(line, contents[cntr])
            cntr += 1

        # Test gzip files
        zip_file = os.path.join(LOG_DIR, LOG_FILE_2[0] + '.gz')
        with gzip.open(zip_file, 'wb') as handle:
            handle.write(LOG_FILE_2[1])
        contents = LOG_FILE_2[1].splitlines(True)
        cntr = 0
        for line in _log_scraper._gen_lines(zip_file):
            self.assertEquals(line, contents[cntr])
            cntr += 1

    def tearDown(self):
        '''Remove any temp files'''
        shutil.rmtree(LOG_DIR)
