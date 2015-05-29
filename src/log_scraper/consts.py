'''
All the consts used by the LogScraper library.
'''

# Where your scraper should look in for files if the user doesn't provide a path themselves
DEFAULT_PATH = 'default_path'
DEFAULT_FILENAME = 'default_filename'

# How many days worth of data is kept in the default_filepath before being moved for archival
DAYS_BEFORE_ARCHIVING = 'days_before_archiving'

# This is needed because files are grabbed from remote boxes over paramiko,
# and the way that's done is by getting a list of all files in the default_path using listdir(),
# and then running a regex over that list to get the files we care about.
# All this because paramiko has no way to get a list of files with a wildcard in the filename
FILENAME_REGEX = 'filename_regex'

# If this key is set to true, the scraper will copy files if a value for 'level' is specified,
# even if the box mapping for 'level' is the same as the host we're currently on.
# Mostly, I'm adding this so that I can write unit-tests for copying
FORCE_COPY = 'force_copy'

# Mapping of what level corresponds to what boxname, so that users can just say things like
# --sandbox or --production.

LEVELS_TO_BOXES = 'levels_to_boxes'

# Files copied over remotely are automatically refreshed if the timestamp on the local copy
# is older than the value for LOCAL_COPY_LIFETIME, which is specified in hours
# Defaults to 0, so that remote files are always refreshed
LOCAL_COPY_LIFETIME = 'local_copy_lifetime'

# Where to copy over any files grabbed over SSH
TMP_PATH = 'tmp_path'

# How many processors to use while doing multiprocessing on the files
PROCESSOR_COUNT = 'processor_count'

# Defaults
OPTIONAL_PARAMS = {DAYS_BEFORE_ARCHIVING : 0, FILENAME_REGEX : '',
                   LEVELS_TO_BOXES : {}, LOCAL_COPY_LIFETIME : 0,
                   TMP_PATH : '', PROCESSOR_COUNT : 4,
                   FORCE_COPY : False}

# Misc useful params you could query the user for
DATE = 'date'

# Runs logger in debug mode
DEBUG = 'debug'

# Override any default filelist in favor of whatever the user gives
FILENAME = 'filename'

FILE_HITS = 'file_hits'

# What production level box to look on
LEVEL = 'level'

# The scraper only prints stats to console if this key is set to True
PRINT_STATS = 'print_stats'

# The keys used in the dicts that store the extracted data
REGEXES = 'regexes'
GROUP_HITS = 'group_hits'
TOTAL_HITS = 'total_hits'

# Stats dict
MAX_KEY = 'max_key'
MIN_KEY = 'min_key'
MAX_COUNT = 'max_count'
MIN_COUNT = 'min_count'
AVG_COUNT = 'avg_count'
