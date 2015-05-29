'''
Log Scraper

Dependencies:
    * Python 2.7
    * paramiko for SSHing to remote hosts

The LogScraper class provides a plug and play experience to mine data from logs.
So long as you give it a regex and a file to run on, you'll be good to go.
You can also build your own scraper on top of the LogScraper class.
For example, if you want to create a scraper that always runs the same regexes
on the same files (unless the user requests otherwise), you can override
the _init_regexes method in your own derived class.

There are a host of extra parameters you can set when creating your scraper.
For a full list with explanations, please see the log_scraper_consts module.

For stats aggregation, just create named groups in your regexes.
The scraper will then aggregate all hits for each value of each named group.

If run on several files, the returned dataset will be the aggregated data
from all the files for each regex, along with each individual file's data.

For usage examples, please see the unit-tests.
'''

from Crypto.pct_warnings import CryptoRuntimeWarning
from datetime import date
from glob import glob
from multiprocessing import Pool
from operator import itemgetter
import collections
import contextlib
import copy_reg
import gzip
import logging
import os
import re
import socket
import sys
import threading
import time
import types
import warnings
import src.log_scraper.consts as LSC

# C'est la vie...
warnings.filterwarnings('ignore', category=CryptoRuntimeWarning)
import paramiko

LOGGER = logging.getLogger('log_scraper')
_LOGGING_SETUP_LOCK = threading.Lock()

class LogScraperException(Exception):
    '''Base LogScraper Exception class'''
    pass

class BadRegexException(Exception):
    '''Use for anything to do with bad regexes'''
    pass

class MissingArgumentException(LogScraperException):
    '''Use to let caller know they didn't provide a required argument'''
    pass

class InvalidArgumentException(LogScraperException):
    '''Use to let the caller know of any bad arguments'''
    pass

class RegexObject(object):
    '''
    A wrapper around a regex pattern.
    Also provides an easy way to get all the named groups from the regex,
    which you can then use for aggregation or what have you
    '''
    def __init__(self, name=None, pattern=None):
        '''
        Initialize the object.
        Throws BadRegexException if the user gives a bad pattern.
        '''
        self.name = name
        self._pattern = pattern
        self._matcher = None
        self._create_matcher()

    def __repr__(self):
        return 'RegexObject(name={}, pattern={})'.format(self.name, self._pattern)

    def __str__(self):
        '''Pretty print info about self'''
        return 'Pattern: {}, Groups: {}'.format(self._pattern, self._matcher.groupindex.keys())

    def _create_matcher(self):
        '''
        Compile the regex pattern and update the matcher member variable.
        Throws BadRegexException if the user gives a bad pattern.
        '''
        try:
            self._matcher = re.compile(self._pattern)
        except Exception:
            raise BadRegexException('Invalid pattern: {}. '
                                    'Could not create matcher'.format(self._pattern))

    def get_matcher(self):
        '''Returns the matcher object'''
        return self._matcher

    def get_pattern(self):
        '''Returns the pattern'''
        return self._pattern

    def update_pattern(self, pattern):
        '''
        Reset the regex pattern, the compiled matcher and the group dicts.
        Throws BadRegexException if the user gives a bad pattern.
        '''
        self._pattern = pattern
        self._create_matcher()

    def get_groups(self):
        '''Returns a list of all named groups found in the regex'''
        return self._matcher.groupindex.keys()


def _pickle_method(method):
    '''
    Define pickling for a custom method and register it.
    This is needed because multiprocessing needs to be able to
    pickle/unpickle the various LogScraper methods while
    processing files in parallel.
    '''
    if method.im_self is None:
        return getattr, (method.im_class, method.im_func.func_name)
    else:
        return getattr, (method.im_self, method.im_func.func_name)

copy_reg.pickle(types.MethodType, _pickle_method)

class LogScraper(object):
    '''
    Base class for a log scraper.
    Takes care of everything for you, so long as you provide regexes to run.
    If your regexes have named groups in them, it will aggregate stats for
    each value found for each named group.
    You can set defaults for where the logfile(s) live,
    as well as where the archived files live.
    You can specify how many days worth of data is kept before archiving,
    so that it knows where to look for the files.
    Wildcards are acceptable in filepaths.
    If files are to be grabbed from various boxes,
    it will copy them over to your specified temporary space;
    this is faster than just keeping the file open over SSH.
    By default, it will refresh the temporary files if they are older than an hour.
    Data is returned as a python dict mapping the regexes run to the stats found.
    You can print to console by setting the PRINT_STATS key in the options dict,
    or just request the data as a dict to work with.
    '''

    COLORS = {
        'HEADER' : '\033[95m',
        'BLUE' : '\033[94m',
        'GREEN' : '\033[92m',
        'WARNING' : '\033[93m',
        'RED' : '\033[91m',
        'ENDC' : '\033[0m'
        }

    def __init__(self, default_filepath=None, optional_params=None, user_params=None):
        '''
        default_filepath - Should be a dict containing key-value pairs for:
          {LSC.DEFAULT_PATH : <directory_where_logs_live>,
           LSC.DEFAULT_FILENAME : <filename_of_log_file>}
          Wildcards are allowed in the filename.

        optional_params - Dict that specifies some optional stuff for your scraper.
          These should be values that are constant for your scraper
          and are not invocation dependent.
          For the common optional params, see LSC.OPTIONAL_PARAMS.

        user_params - Dict of all values that are invocation-dependent
        '''
        if default_filepath is None:
            default_filepath = {}
        self._default_path = default_filepath.get(LSC.DEFAULT_PATH, '')
        default_filename = default_filepath.get(LSC.DEFAULT_FILENAME, '')

        self._default_filename, self._default_ext = os.path.splitext(default_filename)
        self._user_params = user_params if user_params else {}
        self._optional_params = {}

        self._init_logger()

        self._init_optional_params(optional_params)
        self._validate_user_params()

        self._regexes = []
        self._init_regexes()

        self._file_list = []

    def __repr__(self):
        return ('LogScraper(default_filename={}, default_filepath={}, '
                'optional_params={}, '
                'user_params={}'.format(self._default_filename, self._default_path,
                                        self._optional_params, self._user_params))


    def __str__(self):
        return ('Regexes: {}\n'
                'Default filename: {}\n'
                'Default filepath: {}\n'
                'Optional params: {}\n'
                'User params: {}'.format(self._regexes, self._default_filename,
                                         self._default_path, self._optional_params,
                                         self._user_params))

# public:

    def add_regex(self, name, pattern):
        '''
        Add a regex to the list of regexes to run.
        Throws BadRegexException if the user gives a bad pattern.
        '''
        self._regexes.append(RegexObject(name=name, pattern=pattern))

    def clear_regexes(self):
        '''Resets the list of regexes to run'''
        self._regexes = []

    def get_log_data(self):
        '''
        Main driver function for scraping logs.
        Returns the data as a dict
        '''

        #Make sure there's some files to run on
        self._file_list = self._get_file_list()
        try:
            self._validate_file_list()
        except InvalidArgumentException as err:
            LOGGER.error('InvalidArgumentException: %s', err)
            return None

        regex_hits = {}
        regex_hits[LSC.REGEXES] = {}

        for regex in self._regexes:
            regex_hits[LSC.REGEXES][regex.name] = {}
            regex_hits[LSC.REGEXES][regex.name][LSC.GROUP_HITS] = {}
            for group in regex.get_groups():
                regex_hits[LSC.REGEXES][regex.name][LSC.GROUP_HITS][group] = collections.OrderedDict()

        if self._user_params.get(LSC.DEBUG):
            self._print_regex_patterns()

        results = self._multiprocess_files()

        if results is None:
            return None

        for result in results:
            for regex_name, group_hits in result[LSC.REGEXES].items():
                self._combine_group_hits(group_hits, regex_hits[LSC.REGEXES][regex_name])

        #Sort the group data
        for hits in regex_hits[LSC.REGEXES].values():
            if LSC.GROUP_HITS in hits:
                for group, group_hits in hits[LSC.GROUP_HITS].items():
                    hits[LSC.GROUP_HITS][group] = collections.OrderedDict(sorted(group_hits.iteritems()))

        if len(results) > 1:
            regex_hits[LSC.FILE_HITS] = results

        return regex_hits

    def get_regexes(self):
        '''Returns the list of regexes stored'''
        return self._regexes

    def get_user_params(self):
        '''Getter for user_params'''
        return self._user_params

    def print_stats_per_file(self, regex_hits):
        '''Prints stats for each file separately'''
        if regex_hits is None:
            return
        for result in regex_hits[LSC.FILE_HITS]:
            print 'File: {}\n'.format(result[LSC.FILENAME])
            self._pretty_print(result[LSC.REGEXES], self._user_params)

    def print_total_stats(self, regex_hits):
        '''Prints the total stats'''
        if regex_hits is None:
            return
        self._pretty_print(regex_hits[LSC.REGEXES], self._user_params)
        for regex_name, hits in regex_hits[LSC.REGEXES].items():
            print self.COLORS['GREEN']
            print 'Total hits for regex {}: {:,}'.format(regex_name.capitalize(),
                                                         hits[LSC.TOTAL_HITS])
        print self.COLORS['ENDC']


    def set_user_params(self, user_params):
        '''
        Setter for the user params
        Throws: InvalidArgumentException
        '''
        self._user_params = user_params
        self._validate_user_params()

    def view_regex_hits(self, out=sys.stdout):
        '''
        Prints out all lines that match all regexes on all files
        '''

        #Make sure there's some files to run on
        self._file_list = self._get_file_list()
        try:
            self._validate_file_list()
        except InvalidArgumentException as err:
            LOGGER.error('InvalidArgumentException: %s', err)
            return None

        if self._user_params.get(LSC.DEBUG, None):
            self._print_regex_patterns()
        for logfile in self._file_list:
            self._print_regex_matches(logfile, out)

# private:

# Methods you should implement for your own scraper
    def _init_regexes(self):
        '''This is where you write the logic for what regexes to run'''
        pass


    def _get_archived_file_path(self):
        '''Should return where your archived files live'''
        pass

    def _validate_user_params(self):
        '''
        Make sure that all user-given values make sense.
        Should throw InvalidArgumentException with a descriptive message otherwise.
        Call this in your derived class constructor.'''
        pass
######

    def _init_base_logger(self):
        '''Creates the base logger'''
        log_level = logging.INFO
        if self._user_params.get(LSC.DEBUG, None):
            log_level = logging.DEBUG

        LOGGER.setLevel(log_level)
        # create console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        # create formatter
        formatter = logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s',
                                      datefmt='%Y%m%d %H:%M:%S')
        # add formatter to ch
        handler.setFormatter(formatter)
        # add ch to logger
        LOGGER.addHandler(handler)

    def _init_logger(self):
        '''Sets the format of the logging'''
        with _LOGGING_SETUP_LOCK:
            if not LOGGER.handlers:
                self._init_base_logger()
            LOGGER.propagate = False
            # Set paramiko logging to only show warnings and higher
            paramiko_logger = logging.getLogger("paramiko")
            if paramiko_logger.level == logging.NOTSET:
                paramiko_logger.setLevel(logging.WARNING)

    def _init_optional_params(self, opt):
        '''
        Initializes all optional params with given values or defaults.
        '''
        if opt is None:
            opt = {}
        for param, default in LSC.OPTIONAL_PARAMS.items():
            self._optional_params[param] = opt.get(param, default)

    def _are_logs_archived(self, log_date):
        '''
        Returns whether logs are on netapp or on local box.
        Always returns false if days_before_archiving is zero.
        '''

        if self._optional_params[LSC.DAYS_BEFORE_ARCHIVING] == 0 or log_date is None:
            return False

        today = date.today()
        date_obj = date(int(log_date[:-4]), int(log_date[-4:-2]), int(log_date[-2:]))

        delta = today - date_obj
        if delta.days > self._optional_params[LSC.DAYS_BEFORE_ARCHIVING]:
            return True

        return False

    @classmethod
    def _calc_stats(cls, items):
        '''Calculates the min, max and average items processed per key'''

        ret_dict = {LSC.MAX_KEY : 0, LSC.MIN_KEY : 0, LSC.MAX_COUNT : 0,
                    LSC.MIN_COUNT : 0, LSC.AVG_COUNT : 0}

        if items is None or len(items) == 0:
            return ret_dict

        max_key, max_count = max(items.iteritems(), key=itemgetter(1))
        min_key, min_count = min(items.iteritems(), key=itemgetter(1))
        total = sum(items.itervalues())
        count = len(items)

        avg_count = float(total)/count

        ret_dict[LSC.MAX_KEY] = max_key
        ret_dict[LSC.MIN_KEY] = min_key
        ret_dict[LSC.MAX_COUNT] = max_count
        ret_dict[LSC.MIN_COUNT] = min_count
        ret_dict[LSC.AVG_COUNT] = avg_count

        return ret_dict

    @classmethod
    def _combine_group_hits(cls, match_groups, combining_dict):
        '''
        Aggregates all matches for each key found in match_groups
        into combining_dict
        '''

        for group, hits in match_groups.items():
            if isinstance(hits, collections.Mapping):
                if combining_dict.get(group, None) is None:
                    combining_dict[group] = {}

                cls._combine_group_hits(match_groups[group], combining_dict[group])
            else:
                if combining_dict.get(group, None):
                    combining_dict[group] += hits
                else:
                    combining_dict[group] = hits

    @classmethod
    def _copy_remote_file(cls, filepath, local_file, box):
        '''Creates an SSH connection and copies filepath to local_file'''
        ssh = cls._open_ssh_connection(box)
        if ssh is None:
            return ''
        with contextlib.closing(ssh):
            with contextlib.closing(ssh.open_sftp()) as sftp:
                #Temporarily copy file to current box.
                #This is being done because reading the file over SSH
                #slows everything down insanely.
                sftp.get(filepath, local_file)

    def _gen_lines(self, filename):
        '''Generator that yields one line at a time from a file'''
        with self._get_file_handle(filename) as handle:
            for line in handle:
                yield line

    def _get_box_from_level(self, level):
        '''Returns the mapped box name for the given production level'''
        return self._optional_params[LSC.LEVELS_TO_BOXES].get(level, None)

    @classmethod
    def _get_file_handle(cls, log_file):
        '''
        Returns a handle connected to the given file.
        Needed because it grabs over ssh if needed,
        and also checks to see if the given file is a gzip file,
        in which case, some fancy stuff is needed to open it properly.
        The first two characters of the header are inspected to see
        whether the file is a gzipped file or plaintext.
        '''
        LOGGER.info('Opening file %s', log_file)

        handle = open(log_file, 'rb')
        if handle.read(2) == '\x1f\x8b':
            handle.seek(0)
            handle = gzip.GzipFile(fileobj=handle)
        else:
            handle.seek(0)
        return handle

    def _get_file_list(self):
        '''Checks the default filename or wildcard search and the prod level set,
           and returns a list of all files found on the relevant box at the
           given path. If no level value is given, looks on current box'''

        file_list = list()
        level = self._user_params.get(LSC.LEVEL, None)
        log_date = self._user_params.get(LSC.DATE, None)
        filename = self._user_params.get(LSC.FILENAME, None)

        if (level is not None
                and not self._are_logs_archived(log_date)):
            if (self._optional_params.get(LSC.FORCE_COPY, False)
                    or socket.gethostname() != self._get_box_from_level(level)):
                ssh = self._open_ssh_connection(self._get_box_from_level(level))
                if ssh is None:
                    return file_list
                with contextlib.closing(ssh):
                    with contextlib.closing(ssh.open_sftp()) as sftp:
                        filename_regex = self._make_file_name(self._optional_params[LSC.FILENAME_REGEX],
                                                              log_date, level)

                        files = sftp.listdir(self._default_path)
                        for name in files:
                            match = re.match(filename_regex, str(name))
                            if match is not None:
                                file_list.append(os.path.join(self._default_path, match.group()))
                        sftp.close()
                        ssh.close()
                        return file_list

        #By default, let's look at the default_filepath
        if filename is None:
            filename = self._make_file_path()
            file_list = glob(filename)

        else:
            files = filename.split(',')
            for file_iter in files:
                file_list += glob(file_iter)
        file_list = sorted([f for f in file_list if os.path.isfile(f)])

        return file_list

    def _get_log_file(self, log_file):
        '''
        Copies the log file from the appropriate box to local temp space.
        Returns path to local file.
        Doesn't copy if it finds a local file already that is less than
        local_copy_lifetime_in_hours,
        which is an int value specifying how many hours before we recopy.
        '''
        level = self._user_params.get(LSC.LEVEL, None)
        debug = self._user_params.get(LSC.DEBUG, None)

        remote_file = os.path.split(log_file)[1]
        local_filepath = os.path.join(self._optional_params[LSC.TMP_PATH],
                                      '_'.join([level, remote_file]))

        mtime = 0
        if os.path.exists(local_filepath):
            mtime = os.path.getmtime(local_filepath)

        try:
            now = time.time()
            max_time_before_recopy = now - self._optional_params[LSC.LOCAL_COPY_LIFETIME]*60*60

            if mtime < max_time_before_recopy:
                if os.path.exists(local_filepath):
                    os.remove(local_filepath)
                if debug:
                    LOGGER.debug('Copying file from %s:%s to %s temporarily',
                                 self._get_box_from_level(level),
                                 log_file,
                                 local_filepath)
                self._copy_remote_file(log_file, local_filepath,
                                       self._get_box_from_level(level))
                if debug:
                    LOGGER.debug('Done copying file')
        except IOError as err:
            LOGGER.error('Couldn\'t copy %s from %s. Error: %s', log_file,
                         self._get_box_from_level(level), str(err))
            return ''

        return local_filepath

    def _make_file_path(self):
        '''Creates and returns the path where files should be globbed for
           for a given date and production level'''
        log_date = self._user_params.get(LSC.DATE, None)
        level = self._user_params.get(LSC.LEVEL, None)
        if log_date is None and level is None:
            return os.path.join(self._default_path,
                                self._make_file_name(self._default_filename))

        if not self._are_logs_archived(log_date):
            return os.path.join(self._default_path,
                                self._make_file_name(self._default_filename,
                                                     log_date,
                                                     self._get_box_from_level(level)))

        return os.path.join(self._get_archived_file_path(),
                            self._make_file_name(self._default_filename,
                                                 log_date, self._get_box_from_level(level))
                            + '*')

    def _make_file_name(self, base_name, log_date=None, box=None):
        '''
        Basic implementation: <base_name>-<box_name>-<date>.<default_ext>
        Override if necessary
        Returns the filename that would be appropriate for your logs,
        based on the given base_name, date and level.
        '''
        parts = [base_name]
        if box is not None:
            parts.append(box)
        if log_date is not None:
            parts.append(log_date)
        return '-'.join(parts) + self._default_ext

    def _multiprocess_files(self):
        '''Creates a pool to run through several files at once'''

        pool = Pool(processes=self._optional_params[LSC.PROCESSOR_COUNT])
        pool.daemon = True

        # First copy any remote files as needed and create final file list
        if (self._user_params.get(LSC.LEVEL, None)
                and not self._are_logs_archived(self._user_params.get(LSC.DATE, None))):
            if (self._optional_params.get(LSC.FORCE_COPY, False)
                or socket.gethostname() != self._get_box_from_level(self._user_params.get(LSC.LEVEL, None))):
                file_list = pool.map(self._get_log_file, self._file_list)
                pool.close()
                pool.join()
                self._file_list = sorted(filter(lambda x: x != '', file_list))

        LOGGER.debug('Final file list: %s', self._file_list)

        if self._file_list == []:
            LOGGER.error('No files found to process.')
            return None

        pool = Pool(processes=self._optional_params[LSC.PROCESSOR_COUNT])
        pool.daemon = True
        results = pool.map(self._process_file, self._file_list)
        pool.close()
        pool.join()
        return results

    @classmethod
    def _open_ssh_connection(cls, server):
        '''Creates and returns an SSH connection to the appropriate box'''
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(hostname=server, timeout=300)
            return ssh
        except socket.gaierror as err:
            LOGGER.error('Could not create SSH connection on server %s. Error: %s',
                         server, str(err))
        except paramiko.BadHostKeyException as err:
            LOGGER.error('Could not verify hostkey for server: %s. Error: %s', server, str(err))
        except paramiko.AuthenticationException as err:
            LOGGER.error('Could not authenticate on server: %s. Error: %s', server, str(err))
        except paramiko.SSHException as err:
            LOGGER.error('Could not create SSH connection on server %s. Error: %s',
                         server, str(err))

        return None

    @classmethod
    def _pretty_print(cls, result, options):
        '''
        Pretty prints the stats
        '''

        print cls.COLORS["BLUE"]
        if options[LSC.DEBUG]:
            for regex_name, hits in result.items():
                regex_name = regex_name.capitalize()
                for group, group_hits in hits[LSC.GROUP_HITS].items():
                    if group == LSC.TOTAL_HITS:
                        continue
                    print '\n{} hits per {}:'.format(regex_name, group.capitalize())
                    cls._pretty_print_dict(group_hits)
                    print '\n{} max, min and average:'.format(regex_name)
                    cls._print_max_min_avg(group, cls._calc_stats(group_hits))

                print '\nTotal {} hits: {:,}'.format(regex_name, hits[LSC.TOTAL_HITS])

        print cls.COLORS['ENDC']

    @classmethod
    def _pretty_print_dict(cls, results):
        '''
        Pretty self-explanatory.
        '''
        if results is None:
            return
        for key, val in results.iteritems():
            print "{} : {}".format(key, val)

    @classmethod
    def _print_max_min_avg(cls, group, stats):
        '''Prints the min, max and average stats'''
        print '\nAggregator: {}'.format(group)
        print '\nMax requests processed : {:,}, stat value: {}'.format(stats[LSC.MAX_COUNT],
                                                                       stats[LSC.MAX_KEY])
        print 'Min requests processed : {:,}, stat value: {}'.format(stats[LSC.MIN_COUNT],
                                                                     stats[LSC.MIN_KEY])
        print 'Average requests processed : {:,}'.format(stats[LSC.AVG_COUNT])

    def _print_regex_patterns(self):
        '''Prints all the regex patterns'''
        for regex in self._regexes:
            LOGGER.debug('Running regex: %s', regex.get_pattern())

    def _print_regex_matches(self, logfile, out=sys.stdout):
        '''
        Runs a given regex on contents of given file and prints any found matches
        '''
        try:
            for line in self._gen_lines(logfile):
                for regex in self._regexes:
                    match = regex.get_matcher().search(line)
                    if match is not None:
                        out.write(line)
        except AttributeError as err:
            LOGGER.error('Regex Exception %s: %s, Line %s', type(err), err, line)

    def _process_file(self, log_file):
        '''Extracts the data from the given log_file and returns.
           Override if you need to run several regexes or do any special
           processing on the files.'''

        regex_hits = {LSC.FILENAME : log_file, LSC.REGEXES : {}}
        with self._get_file_handle(log_file) as file_handle:
            for regex in self._regexes:
                regex_hits[LSC.REGEXES][regex.name] = {}
                regex_hits[LSC.REGEXES][regex.name][LSC.TOTAL_HITS] = 0
                regex_hits[LSC.REGEXES][regex.name][LSC.GROUP_HITS] = {}
                for group in regex.get_groups():
                    regex_hits[LSC.REGEXES][regex.name][LSC.GROUP_HITS][group] = {}

            for line in file_handle:
                for regex in self._regexes:
                    hits = regex_hits[LSC.REGEXES][regex.name][LSC.GROUP_HITS]
                    regex_hits[LSC.REGEXES][regex.name][LSC.TOTAL_HITS] += self._run_regex(line,
                                                                                           regex.get_matcher(),
                                                                                           hits)
            #Sort the group data
            for hits in regex_hits[LSC.REGEXES].values():
                for group, group_hits in hits[LSC.GROUP_HITS].items():
                    hits[LSC.GROUP_HITS][group] = collections.OrderedDict(sorted(group_hits.iteritems()))

        return regex_hits

    @classmethod
    def _run_regex(cls, line, matcher, aggregators):
        '''
        Given the text and a regular expression,
        gives back a dict of regex matches found, with the key as a feed
        and the value as the count of matches for that feed.
        '''
        try:
            match = matcher.match(line)
            if match is not None:
                for agg_key, agg_dict in aggregators.items():
                    cls._sum_group_matches(agg_dict, match, agg_key)
                return 1
        except AttributeError as err:
            LOGGER.error('Regex Exception %s: %s, Line: %s', type(err), err, line)
            return None
        return 0

    @classmethod
    def _sum_group_matches(cls, group_sums, match, regex_group):
        '''
        Takes a regex match and a group value and populates the given dict
        with counts for each unique value for the regex group in the match.
        If the regex match fails, returns silently.
        '''

        try:
            key = match.group(regex_group)
            if not key in group_sums:
                group_sums[key] = 1
            else:
                group_sums[key] += 1
        except IndexError:
            return

    def _validate_file_list(self):
        '''Makes sure that there are files to process'''

        if self._file_list == []:
            if self._user_params.get(LSC.FILENAME, None):
                raise InvalidArgumentException('File does not exist at {} '
                                               'Please provide a valid path to a '
                                               'log file.'.format(self._user_params[LSC.FILENAME]))
            else:
                raise InvalidArgumentException(('No files found at {} on {}. '
                                                'Please provide a valid path to a log file.'
                                               ).format(self._make_file_path(),
                                                        'the current box'
                                                        if not
                                                        self._user_params.get(LSC.LEVEL, None)
                                                        else
                                                        self._get_box_from_level(self._user_params[LSC.LEVEL])))

