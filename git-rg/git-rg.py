#!/usr/bin/env python3
# -*- coding: utf-8 -*-

## License:
#
# Copyright (c) 2021 Ilya Burov

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


## References:
#
# https://stackoverflow.com/questions/3134900/join-with-pythons-sqlite-module-is-slower-than-doing-it-manually
# Manual joins with Python are way faster than SQL joins in sqlite

## Caveats:
#
# Some sessions may require LC_ALL environment variable to be set
# to en_US.utf8

"""
Git Access Report Generator
Generates Git access based on data provided by Git log
"""

__author__ = "Ilya Burov"
__version__ = "0.0.1"
__status__ = "Test"

import re
import sys
import os
import io
import json
import resource
import textwrap
import math
import errno

from argparse import ArgumentParser
from typing import List
from typing import Tuple
from typing import Collection
from collections import defaultdict
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from enum import Enum
from enum import unique
from functools import lru_cache
from functools import wraps
from platform import python_version
from pwd import getpwall
from time import localtime
from time import mktime
from time import time
from timeit import Timer
from urllib.parse import urlparse

ENCODING = 'utf-8'

REF_ACCESS_INFO = 'master:access_config.json'
REV_HEAD = 'HEAD'

KEY_AUTHOR_NAME = 'can'
KEY_COMMIT_TIMESTAMP = 'ct'
KEY_USERNAME = 'cu'
KEY_AFFECTED_FILES = 'caf'
KEY_ACTION = 'a'
KEY_TIMERANGE = 'tr'

# Delimiters
D_START = '\u008A'
D_LIST = '\u008B'
D_BOM = '\u008C'
D_EOM = '\u008D'
D_FLD = '\u008E'

# Dates and numbers
# 1/1/1900 00:00:00.0 - The oldest date and time supported by Python
# standard library
MIN_DATE = -2208988800
TTY_WRAP = 100
MSG_INDENT = 8
NAN = float('nan')

# Format string
FLD_REPORT = [
    'uname',
    'hname',
    'event',
    'iotime',
    'cmt_event',
    'cmt_time',
    'pcnt',
    'ish',
    'modfile',
    'tgtfile'
]

FMT_MODRPT = '{event:<6} {uname:<8}\t{hname:<18}\t{iotime:<19}\t{cmt_event:<8}\t{cmt_time:<19}\t{modfile}\t{tgtfile}\r\n'
FMT_USRRPT = '{event:<6}\t{iotime:<19}\t{cmt_event:<8}\t{cmt_time:<19}\t{pcnt:<5}\t{ish:<40}\t{modfile}\t{tgtfile}\r\n'

FMT_DATE_REPORT = '%m/%d/%Y-%H:%M:%S'

FMT_DATE_GIT_LOG = '%Y-%m-%d %H:%M:%S'

FMT_DATE_FILENAME = '%d%m%Y%H%M%S'

FMT_ALLOWABLE_DATE = [
    '%m/%d/%Y',
    '%m-%d-%Y',
    '%m/%d/%Y/%H:%M:%S',
    '%m-%d-%Y-%H:%M:%S',
    FMT_DATE_FILENAME,
    FMT_DATE_GIT_LOG,
    FMT_DATE_GIT_LOG
]

FMT_ALL_FILES = '[ALL FILES IN {!s}]'

# Literal strings
STR_EMP = ''
STR_SPACE = ' '
STR_DASH = '-'
STR_NA = 'N/A'
STR_USER = 'user'
STR_MODULE = 'module'
STR_PARTITION = 'partition'
STR_READ = 'READ'
STR_UPDATE = 'UPDATE'
STR_USER_UNKNOWN = '[unknown]'
STR_PREFIX_UNKNOWN = 'unk:'
STR_LF = '\n'
STR_CRLF = '\r\n'
EXT_ZIP = 'zip'
EXT_TXT = 'txt'
STR_PERIOD = '.'
STR_REPORT = 'report'

# Status
STAT_OK = 'OK'
STAT_FAIL = 'FAIL'
STAT_WARN = 'WARN'
STAT_UNK = 'UNK'

class CLI():
    """CLI class provides certain convenience functions that may be used
    to implement Command line interafce"""

    ESCAPE = '\033[{!s}m'
    ENDC = ESCAPE.format('0')

    BOLD = '1'
    ITALIC = '3'
    UNDERLINE = '4'
    SLOW_BLINK = '5'

    # May not be supported on all systems
    FAINT = '2;'
    FAST_BLINK = '6;'

    COLORS = {
        'black': '30',
        'red': '31',
        'green': '32',
        'yellow': '33',
        'blue': '34',
        'magenta': '35',
        'cyan': '36',
        'white': '37',
    }

    FMT_MSG_PREFIX = '[{}]: '

    @classmethod
    def decorate(cls, string, *style) -> str:
        """Decorates (colorises) the string
        Args:
            string  Text string
            style   Stayle to apply to 'string', colours first, text effects
                    second
        Returns:
            Decorated string.  Note that the length of resulting string
            equals string length plus the length of colour escape sequence
            plus the length of ENDC ('CLI.ENDC') escape sequence
        """

        _style = STR_EMP.join(
            cls.ESCAPE.format(s) for s in style if s is not None
            )
        return f'{_style}{string}{cls.ENDC}'

    @classmethod
    def _wrapmsg(cls, msg: str, prefix: str, *style) -> str:
        '''
        Wraps the string `msg` to a number of characters specified in
        `TTY_WRAP`, prefixes it with `prefix`, applies `*style`, left-aligns
        the message text to number of characters specified in `MSG_INDENT`.
        '''
        _prefix = cls.decorate(prefix, *style)

        # Adjust the prefix alignment
        initlen = (len(_prefix) - len(prefix)) + MSG_INDENT
        fprefix = cls.FMT_MSG_PREFIX.format(_prefix).ljust(initlen)
        subindent = STR_SPACE * (len(fprefix) - (len(_prefix) - len(prefix)))

        # The following is to work around the issue in TextWrapper reported
        # in year 2008. Because of the vague description it looks like it
        # was misunderstood an was not resolved as a result.
        #
        # The reporter describes it as follows:
        # if a piece of text given to textwrap contains one or more "\n",
        # textwrap does not break at that point. I would have expected "\n"
        # characters to cause forced breaks.
        #
        # ---
        #
        # Even though replace_whitespace set to False makes TextWrapper
        # break lines at line feed characters, the subsequent lines are not
        # indented if subsequent_indent is set to True
        #
        # https://bugs.python.org/issue1859

        msg_lines = msg.splitlines()

        out = textwrap.fill(msg_lines[0],
                            width=TTY_WRAP,
                            initial_indent=fprefix)

        for line in msg_lines[1:]:
            out += '\n'
            out += textwrap.fill(line,
                                 width=TTY_WRAP,
                                 initial_indent=subindent,
                                 subsequent_indent=subindent)

        return out


    @classmethod
    def errmsg(cls, msg: str):
        print(cls._wrapmsg(str(msg), 'error', cls.COLORS['red']), file=sys.stderr)


    @classmethod
    def infomsg(cls, msg: str):
        print(cls._wrapmsg(str(msg), 'info', cls.COLORS['blue']))


    @classmethod
    def warnmsg(cls, msg: str):
        print(cls._wrapmsg(str(msg), 'warn', cls.COLORS['yellow']), file=sys.stderr)

    @classmethod
    def importerrmsg(cls, ex: Exception):
        cls.errmsg(f"Failed to import Python module: {ex.name}")

    @classmethod
    def progressmsg(cls, msg: str, newline: bool = False) -> str:
        _end = STR_LF if newline else STR_EMP
        clr = cls.COLORS['blue']
        # Maximum message width: maximum characters per TTY line minus indent
        maxwidth = TTY_WRAP - MSG_INDENT
        # Padding: colour number control escape charaters plus maximum
        # message width
        padding = len(clr) + len(cls.ENDC) + maxwidth
        _msg = textwrap.shorten(msg, width=maxwidth - MSG_INDENT)
        print('\r{:<{}}'.format(cls._wrapmsg(_msg, '>>>>', clr), padding),
              end=_end)


    @classmethod
    def resultmsg(cls, status: str = None, etime: int = -1) -> str:
        _status = status
        if status == STAT_OK or status is None:
            clr = cls.COLORS['green']
        elif status == STAT_FAIL:
            clr = cls.COLORS['red']
        elif status == STAT_WARN:
            clr = cls.COLORS['yellow']
        else:
            _status = STAT_UNK
            clr = cls.COLORS['blue']

        if etime > 0:
            pad = max(5 - len(_status), 1)
            _etime = '{:<{}}ET: {:0.1f}s'.format(STR_EMP, pad, etime)
        else:
            _etime = STR_EMP
        print('[{}]{}'.format(cls.decorate(_status, clr), _etime))

    @classmethod
    def with_progress(cls,
                     initmsg: str = None,
                     successmsg: str = None,
                     retapply: Callable = None) -> Callable:
        def print_status_outer_wrapper(func) -> Callable:
            @wraps(func)
            def print_status_inner_wrapper(*args, **kwargs) -> Callable:
                tafter = 0
                try:
                    fwd_exc = None
                    cls.progressmsg(initmsg or repr(func), False)
                    tbefore = time()
                    ret = func(*args, **kwargs)
                    tafter = time() - tbefore
                    if successmsg is not None:
                        if retapply is not None:
                            cls.progressmsg(
                                successmsg.format(retapply(ret)), False
                            )
                        else:
                            cls.progressmsg(successmsg, False)
                    status = STAT_OK
                except Exception as ex:
                    status = STAT_FAIL
                    fwd_exc = ex
                finally:
                    cls.resultmsg(status, tafter)
                    if fwd_exc is not None:
                        raise fwd_exc
                return ret
            return print_status_inner_wrapper
        return print_status_outer_wrapper


if not sys.platform.startswith('linux'):
    CLI.errmsg("This program can only run on GNU/Linux platforms")
    sys.exit(os.EX_USAGE)
elif sys.hexversion < 0x30409f0:
    CLI.errmsg("Python 3.4.9 or higher is required to run this program")
    sys.exit(os.EX_SOFTWARE)
elif not sys.stdout.encoding.lower().startswith(ENCODING):
    CLI.errmsg(f"Current locale does not support {ENCODING}")
    sys.exit(os.EX_SOFTWARE)


try:
    import git
    import sqlite3
    import git.exc
    from dateutil import parser as dateparser
except ImportError as ex:
    CLI.importerrmsg(ex)
    sys.exit(os.EX_SOFTWARE)



@unique
class Action(Enum):
    """
    Action
    """
    added = (1, 'A')
    badpair = (-1, 'B')
    clone = (9, 'CL')
    copied = (2, 'C')
    deleted = (3, 'D')
    failread = (-10, 'FR')
    failupdate = (-11, 'FU')
    invalid = (-3, 'X')
    modified = (4, 'M')
    read = (6, 'RD')
    renamed = (5, 'R')
    typechg = (7, 'T')
    unknown = (-2, 'UNK')
    update = (8, 'U')

    def __str__(self):
        return self.name

    def __int__(self):
        return self.value[0]

    def __repr__(self):
        return '%s.%s = %s' % (type(self).__name__, self.name, self.value)

    def abbrev(self):
        return self.value[1]

    @classmethod
    def is_read(cls, act):
        return act in (cls.read, cls.clone)

    @classmethod
    def is_update(cls, act):
        return act in (
            cls.update, cls.added, cls.deleted, cls.renamed,
            cls.typechg, cls.modified, cls.copied
        )

    @classmethod
    def is_fail(cls, act):
        return act in (
            cls.failread, cls.failupdate, cls.unknown,
            cls.invalid, cls.badpair
        )

    @classmethod
    def forabbrev(cls, reqabbrev):
        """Gets the action for given abbreviation"""
        for act in cls:
            if act.abbrev() == reqabbrev:
                return act
        return cls.unknown

    @classmethod
    def fornum(cls, reqint):
        """Gets the action for given numeric value"""
        for act in cls:
            if int(act) == reqint:
                return act
        return cls.unknown


class DBInterfaceBase():

    def __init__(self, tabsetup):
        self.db = sqlite3.connect(':memory:', isolation_level='DEFERRED')
        self.cur = self.db.cursor()

        self.table_name = 'events'
        self.table_cols = tabsetup['cols']

        for _key in ('ts', 'user'):
            if _key not in self.table_cols:
                raise KeyError(
                    f'No \'{_key}\' key in table \'{self.table_name}\''
                    )

        for setup_query in tabsetup['pre']:
            self.cur.execute(setup_query)

        query = f'CREATE TABLE {self.table_name} ('
        query += ','.join([
            f'{_name} {_type}' for _name, _type in self.table_cols.items()
            ])
        query += ')'

        self.cur.execute(query)

        for setup_query in tabsetup['post']:
            self.cur.execute(setup_query)


    def get_active_users(self) -> List[str]:
        self.cur.execute(f'SELECT DISTINCT user FROM {self.table_name}')
        return [x[0] for x in self.cur]


    def _get_events_from_query(self, query) -> tuple:
        self.cur.execute(query)
        for row in self.cur:
            yield from self.transform_values(*row)


    def _get_events_interval(self,
                               tsa: int = NAN,
                               tsb: int = NAN,
                               limit: int = 1,
                               user: str = None,
                               action: Action = None) -> tuple:

        cols = ','.join(self.table_cols.keys())

        query = f'SELECT {cols} FROM {self.table_name} WHERE '

        if user is not None:
            query += f'(user = \'{user}\') AND '

        if not math.isnan(tsa) and not math.isnan(tsb):
            query += f'(ts BETWEEN {tsa} AND {tsb}) ORDER BY ts '
        elif not math.isnan(tsa) or not math.isnan(tsb):
            if not math.isnan(tsa):
                query +=  f'(ts > {tsa}) ORDER BY ts ASC LIMIT {limit}'
            else:
                query +=  f'(ts < {tsa}) ORDER BY ts DESC LIMIT {limit}'
        else:
            raise AttributeError('Invalid combintaion of arguments')



        if action is None:
            yield from self._get_events_from_query(query)
        else:
            actnum = int(action)
            for record in self._get_events_from_query(query):
                if record[3] == actnum:
                    yield record


    def get_events_between(self,
                            after: int,
                            before: int,
                            user: str = None,
                            action: Action = None) -> tuple:

        yield from self._get_events_interval(tsa=after,
                                               tsb=before,
                                               user=user,
                                               action=action)


    def get_events_before(self,
                           ts: int,
                           limit: int = 1,
                           user: str = None,
                           action: Action = None) -> tuple:

        yield from self._get_events_interval(tsb=ts,
                                               limit=limit,
                                               user=user,
                                               action=action)


    def get_events_after(self,
                          ts: int,
                          limit: int = 1,
                          user: str = None,
                          action: Action = None) -> tuple:

        yield from self._get_events_interval(tsa=ts,
                                               limit=limit,
                                               user=user,
                                               action=action)

    def transform_values(self, *args) -> tuple:
        raise NotImplementedError()


class Util():
    """Util class. You know... utilities"""

    # DATE OPERATIONS

    @classmethod
    def date_to_ts(cls,
                   datestr: str,
                   fmt: str = None) -> int:

        out_ts = NAN

        if fmt is not None:
            out_ts = cls.__date_to_ts(datestr, fmt)
        else:
            for dformat in FMT_ALLOWABLE_DATE:
                try:
                    out_ts = cls.__date_to_ts(datestr, dformat)
                    if not math.isnan(out_ts) and out_ts >= MIN_DATE:
                        break
                except ValueError:
                    pass

        if math.isnan(out_ts):
            raise ValueError(f'{datestr}: Cannot parse the date string')

        return out_ts


    @staticmethod
    def __date_to_ts(datestr: str, fmt: str) -> int:
        out_datetime = None
        out_ts = NAN

        try:
            out_datetime = datetime.strptime(datestr, fmt)
        except ValueError:
            out_datetime = dateparser.parse(datestr, fuzzy=True)

        if out_datetime is not None:
            out_ts = int(mktime(out_datetime.timetuple()))
        
        return out_ts


    @staticmethod
    def ts_to_dtime(ts: int) -> datetime:
        return datetime.fromtimestamp(ts)


    @classmethod
    def __ts_strftime(cls, sec: int, fmt: str) -> str:
        return cls.ts_to_dtime(sec).strftime(fmt)


    @staticmethod
    def _as_ts(dt: datetime) -> int:
        return int(mktime(dt.timetuple()))


    @classmethod
    def ts_now(cls) -> int:
        return cls._as_ts(datetime.now())


    @classmethod
    def _get_ts(cls, *args) -> int:
        return cls._as_ts(datetime(*args))

    @classmethod
    def get_report_file_path(cls,
                             parent: str = None,
                             prefix: str = STR_REPORT,
                             ext: str = EXT_TXT,
                             after: int = NAN,
                             before: int = NAN):
        filename = prefix
        if not math.isnan(after) and not math.isnan(after):
            filename += '_'
            filename += cls.__ts_strftime(after, FMT_DATE_FILENAME)
            filename += '-'
            filename += cls.__ts_strftime(before, FMT_DATE_FILENAME)
        filename += f'.{ext}'



        if parent is not None:
            _path = os.path.join(parent, filename)
        else:
            _path = filename

        return _path

    @classmethod
    def ts_to_day_beginning(cls, sec: int) -> int:
        date = cls.ts_to_dtime(sec)
        return cls._get_ts(date.year, date.month, date.day)


    @classmethod
    def ts_to_day_end(cls, sec: int) -> int:
        date = cls.ts_to_dtime(sec)
        return cls._get_ts(date.year, date.month, date.day, 23, 59, 59)


    @classmethod
    @lru_cache(maxsize=None)
    def ts_to_report_date(cls, sec: int) -> str:
        return cls.__ts_strftime(sec, FMT_DATE_REPORT)


    @classmethod
    def ts_to_git_date(cls, sec: int) -> str:
        return cls.__ts_strftime(sec, FMT_DATE_GIT_LOG)


    @staticmethod
    def get_peak_rss() -> Tuple[int, int, int]:
        """Gets peak RSS used by current process"""
        rss_self = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_children = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        return tuple(int(rss / 1000) for rss in (
            rss_self + rss_children, rss_self, rss_children)
        )


    @staticmethod
    def isplitlines(buf) -> str:
        ret = ''
        for char in buf:
            if not char == '\n':
                ret += char
            else:
                yield ret
                ret = ''

        # CAVEAT: This prevents the last line from being
        #         yielded if it is empty.
        if ret:
            yield ret


    @staticmethod
    def ireadlines(fpath) -> str:
        with open(fpath, 'r') as fd:
            yield from fd



class UsernameProcessor():

    def __init__(self,
                 dictionary: Collection = None,
                 replacements: dict = None,
                 threshold_factor: int = 70):

        self.dictionary = set()
        if dictionary is not None:
            self.update_dictionary(*dictionary)

        self.replacements = {}
        if replacements is not None:
            self.update_replacements(replacements)

        self.threshold_factor = threshold_factor



    def update_dictionary(self, *args: str):
        """Sets the dictionary of words used by Util.correct_name"""
        self.dictionary.update(args)


    def update_replacements(self, *args: str):
        """Sets the dictionary of words used by Util.correct_name"""
        self.replacements.update(args)


    @staticmethod
    def get_pw_entries() -> dict:
        ret = {}
        for pw in getpwall():
            ret[pw.pw_name] = pw.pw_gecos
        return ret


    @lru_cache(maxsize=None) # TODO: replace
    def username_to_humanname(self, username: str):
        ret = None
        pwname = self.get_pw_entries().get(username)
        if pwname is not None and pwname:
            ret = self.correct(pwname)
        else:
            ret = f'[{username}]'

        return ret


    @lru_cache(maxsize=None) # TODO: replace
    def humanname_to_username(self, hname: str):
        """Matches username against pwd entries, and gets corresponding
        human name
        """
        
        ret = None
        for u, h in self.get_pw_entries().items():
            if h == hname or self.correct(h) == self.correct(hname):
                ret = u
                break

        if ret is None:
            ret = f'[{hname}]'

        return ret


    @staticmethod
    def strip_nonalnum(string, *excl: str) -> str:
        """Strips 'string' off non-alphanumeric characters and spaces,
        excluding any characters in variadic arguments passed
        """
        out = ''
        for c in string:
            _ord = ord(c)
            if (65 <= _ord <= 90) or (97 <= _ord <= 122) or c in excl:
                out += c
        return out


    @staticmethod
    def same_letters_percentage(x: str, y: str) -> float:

        _x, _y = (w.lower() for w in (x, y))
        max_len = max(len(_x), len(_y))
        intersect_len = len([value for value in _x if value in _y])

        return max(intersect_len, 0) / max_len * 100


    @staticmethod
    def similarity_percentage(x, y) -> float:
        """Gets a factor by which the string 'dw' matches the string 'gw'
        """
        what, against = (w.lower() for w in (x, y))
        wlen, alen = (len(w) for w in (what, against))
        if wlen > alen:
            what, against = against, what
            wlen, alen = alen, wlen

        match = 0
        nonmatch = 0
        if what != against:
            for shift in range(0, (alen - wlen) + 1):
                if match == wlen:
                    break
                # if more than two consecutive characters did not match,
                # then assume that this portion did not match
                if nonmatch > 2:
                    match = match - 1
                    nonmatch = 0
                for i in range(0, wlen):
                    if what[i] == against[i + shift]:
                        match += 1
                    else:
                        nonmatch += 1
        else:
            if alen == wlen == 0:
                match = 1
            else:
                match = wlen

        return max(match, 0) / max(alen, wlen) * 100


    @classmethod
    def match_factor(cls, x, y):
        sim_pcnt = cls.similarity_percentage(x, y)
        same_ltr_pcnt = cls.same_letters_percentage(x, y)
        return max((sim_pcnt + same_ltr_pcnt) / 2, sim_pcnt)


    @classmethod
    def normalize(cls, s) -> str:
        """Removes extra whitespace and non-aplhanumeric characters for a
        string 's' representiang a human name
        """
        return STR_SPACE.join(cls.strip_nonalnum(p) for p in s.split() if p)

    @lru_cache(maxsize=None)
    def correct(self, word: str):
        ret = word
        if word in self.replacements:
            ret = self.replacements[word]
        else:
            highest_factor = 0
            word_ascii = self.normalize(word)
            for dictword in self.dictionary:
                factor = self.match_factor(dictword, word_ascii)
                if factor > highest_factor:
                    highest_factor = factor
                    if highest_factor >= self.threshold_factor:
                        ret = dictword
                        break
        return ret



class GitRepoDataParser(DBInterfaceBase):
    '''
    Git repository data parser.
    See:
       - https://github.com/gitpython-developers/GitPython
       - https://pypi.org/project/GitPython
    '''

    TABLE_SETUP = {
        'cols': OrderedDict([
            ('ish', 'VARCHAR(40) PRIMARY KEY UNIQUE NOT NULL'),
            ('user', 'VARCHAR(32) NOT NULL'),
            ('ts', 'INTEGER NOT NULL'),
            ('af', 'TEXT NOT NULL')
        ]),
        'pre': ['PRAGMA synchronous = OFF'],
        'post': []

    }

    def __init__(self, path_repo: str):
        """
        path_repo - A git repository path
        """
        super().__init__(__class__.TABLE_SETUP)

        self.git = git.Git(path_repo)
        self.repo = git.Repo(path_repo)


    def get_version(self):
        '''
        Returns the `git` command version as `str`
        '''

        full_ver = self.version()

        # Trimmed git version i.e. digits only.
        trim_ver = re.search(r'\b[\d.]+', full_ver).group(0)

        return trim_ver if trim_ver.replace('.', '').isdigit() else full_ver


    def get_remote_url(self):
        '''
        Returns the URL of remote as `str`
        '''

        return urlparse(self.git.remote('get-url', '--push', 'origin'))


    def get_remote_path(self):
        '''
        Returns the path of remote as `str`
        '''
        return self.get_remote_url().path


    def is_dirty(self):
        '''
        Returns `True` is the repository is dirty, `False` otherwise
        '''

        return self.repo.is_dirty()

    def get_size_at_rev(self, rev : str = 'HEAD'):
        # self.git
        # git rev-list --objects --all <REV> | git cat-file --batch-check="%(objectsize:disk) %(rest)" | cut -d" " -f1 | paste -s -d + - | bc
        pass



    def get_size(self):
        '''
        Returns the total size (packed) of all objects in repository as `int`
        '''
        for line, _, count in (
            x.partition(':') for x in self.git.count_objects('-v').splitlines()
            ):
            if line.strip() == 'size-pack':
                strcount = count.strip()
                if strcount.isdigit():
                    return 1000 * int(count.strip())
        raise ValueError


    def get_full_tree(self,
                      rev: str = None,
                      recurse: bool = False,
                      otype: str = None):
        '''
        Yields the full tree of Git repository at specific revision as `str`

        Args:
            recurse     If `True` get the tree with all sub-trees
                        recursively.

            rev         Revision ID to get the tree at.
                        Defaults to HEAD if evaluated to `False`
                        (empty, None, False, etc.)
        '''

        lstree_cmd = []
        if recurse:
            lstree_cmd.append('-r')
        lstree_cmd.extend(['--full-tree', rev or REV_HEAD])

        # There is a Repo.tree() method in gitpython:
        # [o.path for o in self.repo.tree(rev).traverse() if o.type == otype]
        # However, lists work better than iterators/generators when parsing
        # command's output
        # outlist = []
        for entry in Util.isplitlines(self.git.ls_tree(*lstree_cmd)):
            splitentry = entry.rsplit(None, 4)
            if otype and splitentry[1] == otype:
                yield splitentry[3]
                continue
            yield splitentry[3]

    @lru_cache(maxsize=2)
    def get_blobs_before(self, ts: int):
        '''
        Yields the names of all files that exist in the repository before or
        at the time soecified as `ts`
        '''

        yield from Util.isplitlines(self.git.ls_tree(
            '--full-tree',
            '--name-only',
            '-r',
            tuple(self.get_events_before(ts))[0][0]
        ))


    def get_authors(self):
        """Gets the list of all authors as `list`"""
        regex = re.compile(r'\s*\d*\t')
        return set(
            (regex.split(s)[1] for s in self.git.shortlog('-sn').splitlines())
        )


    def get_access_info(self):
        """Gets the access information dictionary as `dict`.  Returns empty
        `dict` if access information file is not found
        """
        accessinfo_str = self.show(REF_ACCESS_INFO)
        return json.loads(accessinfo_str) if accessinfo_str else {}


    @CLI.with_progress("Analysing Git repository history...",
                  "{:d} Git commit records analysed",
                  int)
    def parse_log(self, after: int, before: int):
        """Reads and parses commit records fro Git repository.  See
        https://git-scm.com/docs/pretty-formats for pretty-formatting details
        """
        git_log_cmd = [
            '--raw',
            '--no-merges',
            '--abbrev-commit',
            '--numstat',
            f'--format={D_START}{D_BOM}%H{D_FLD}%an{D_FLD}%ct{D_EOM}{D_LIST}',
            '--word-diff=porcelain',
            '--name-status'
        ]

        if after >= MIN_DATE:
            git_log_cmd.append(
                '--after={}'.format(Util.ts_to_git_date(after))
            )

        if before >= MIN_DATE:
            git_log_cmd.append(
                '--before={}'.format(Util.ts_to_git_date(before))
            )

        # Parsing commit records
        ctr = 0
        for line in self.git.log(*git_log_cmd).split(D_START):
            git_commit_body_split = line.split(D_LIST)
            # If there is a file list
            if len(git_commit_body_split) == 2:

                # git_commit_body_split is two elements long
                commit_description, file_list = git_commit_body_split

                # For each line in the file list portion of git log output,
                # if both parts of line (before and after a tab character)
                # are not empty then add split line to list else discard line
                ish, user, commit_ts_s = commit_description \
                        .replace(D_BOM, STR_EMP) \
                        .replace(D_EOM, STR_EMP) \
                        .split(D_FLD)
                ts = int(commit_ts_s)

                files = json.dumps([
                    [act for act in line.split('\t', 2) if act]
                        for line in Util.isplitlines(file_list) if line
                ])

                try:
                    self.cur.execute(f'''
                        INSERT INTO {self.table_name}
                            VALUES ('{ish}', '{user}', {ts}, '{files}')
                    ''')
                    ctr += 1
                except sqlite3.IntegrityError:
                    # Deliberately ignoring and hoping that we got here
                    # because a uniqe constraint was just violated and it's
                    # ok.
                    pass

        self.db.commit()

        return ctr


    def transform_values(self, *args):
        # 0 - ish
        # 1 - user
        # 2 - timestamp
        # 3 - affected files, JSON-serialized list of lists

        ish = args[0]

        user = args[1]

        ts = args[2]

        af = args[3]

        file_events = json.loads(af)
        for file_event in file_events:
            act = Action.forabbrev(file_event[0][0])
            actnum = int(act)

            _pcnt = file_event[0][1:]

            if _pcnt.isdigit():
                pcnt = '{}%'.format(_pcnt.lstrip('0'))
            else:
                pcnt = None

            modfile = file_event[1]

            if len(file_event) == 3:
                tgtfile = file_event[2]
            else:
                tgtfile = None

            yield (ish, ts, user, actnum, pcnt, modfile, tgtfile)


class PhabricatorAccessLogParser(DBInterfaceBase):
    """
    Phabricator SSH log reader
    """

    TABLE_SETUP = {
        'cols': OrderedDict([
            ('user', 'VARCHAR(32) NOT NULL'),
            ('ts', 'INTEGER NOT NULL'),
            ('act', 'INTEGER NOT NULL'),
            ('bc', 'INTEGER NOT NULL')
        ]),
        'pre': ['PRAGMA synchronous = OFF'],
        'post': ['''CREATE UNIQUE INDEX unique_rec_constraint
                    ON events (user, ts, act)''']

    }

    def __init__(self, logpath: str):
        """
        logpath is a Pahbricator SSH access log path
        """
        super().__init__(__class__.TABLE_SETUP)
        self.logpath = logpath


    @CLI.with_progress("Analysing Phabricator SSH access log...",
                  "{:d} Phabricator SSH access log records analysed",
                  int)
    def parse_log(self,
                  after: int,
                  before: int,
                  thrs_upd: int = 32,
                  thrs_read: int = 32,
                  path_repo: str = None) -> int:

        ctr = 0

        for logline in Util.ireadlines(self.logpath):
            vals = logline.split('\t')
            # #  F  Description                                Example
            # -  -- -----------------------------------------  -----------------------------------
            # 0  %D The request date.                          [Fri, 09 Feb 2034 09:42:05 -0500]
            # 1  %p The PID of the server process.             1869
            # 2  %h The webserver's host name.                 example.com
            # 3  %r The remote IP.                             127.0.0.1
            # 4  %s The system user.                           git
            # 5  %S The system sudo user.                      phd
            # 6  %u The logged-in username, if any.            janedoe
            # 7  %C The workflow which handled the request.    git-upload-pack
            # 8  %U The request path, or request target.       git-upload-pack /source/project.git
            # 9 %c The HTTP response code or proc. exit code. 0
            # 10 %T The request duration, in microseconds.     123344
            # 11 %i Request input, in bytes.                   4
            # 12 %o Request output, in bytes.                  920

            # '[%D]\t%p\t%h\t%r\t%s\t%S\t%u\t%C\t%U\t%c\t%T\t%i\t%o'

            if len(vals) != 13:
                continue

            # Date and timestamp in milliseconds to correlate with git events
            date = vals[0].split()
            ts = Util.date_to_ts(STR_SPACE.join(date[1:5]))

            if before >= ts >= after:

                # Username
                user = vals[6]

                # Remote workflow
                rcmd = vals[7]

                # Remote command
                remote_cmd = vals[8].split(None, 1)

                # Number of inbound and outbound bytes
                bytes_in = int(vals[11]) if vals[11].strip().isdigit() else 0
                bytes_out = int(vals[12]) if vals[12].strip().isdigit() else 0

                # Byte count, either inbound or outbound
                # Used to determine whether or not a particular event was a
                # clone furter in the algorithm
                bc = 0

                # Ignore events not related to specified remote
                if len(remote_cmd) == 2:
                    wfpath = remote_cmd[1]
                    if path_repo is not None and wfpath != path_repo:
                        continue

                    try:
                        st_resp = int(vals[9])
                    except ValueError as ex:
                        continue


                    # Read event
                    if rcmd == 'git-upload-pack' and bytes_out > thrs_read:
                        if st_resp == 0:
                            act = Action.read
                        else:
                            act = Action.failread

                        bc = bytes_out

                    # Update event
                    elif rcmd == 'git-receive-pack' and bytes_in > thrs_upd:

                        if st_resp == 0:
                            act = Action.update
                        else:
                            act = Action.failupdate

                        bc = bytes_in
                    else:
                        # Ignore unknown actions
                        continue

                    actnum = int(act)

                    try:
                        self.cur.execute(f'''
                            INSERT INTO {self.table_name}
                            VALUES ('{user}', {ts}, '{actnum}', {bc})
                            ''')
                        ctr += 1
                    except sqlite3.IntegrityError as ex:
                        # Deliberately ignoring and hoping that we got here
                        # because a uniqe constraint was just violated and
                        # it's ok.
                        pass

        self.db.commit()

        return ctr


    def transform_values(self, *args):

        ts = int(args[1])
        act = int(args[2])
        # 0 - user
        # 1 - timestamp
        # 2 - action
        # 3 - byte count

        yield (args[0], ts, act, args[3])


class AuditReportGenerator():

    def __init__(self,
                 vcs_parser: DBInterfaceBase,
                 access_parser: DBInterfaceBase,
                 username_processor: UsernameProcessor,
                 after: int,
                 before: int):

        super().__init__()
        self.vcs_parser = vcs_parser
        self.access_parser = access_parser
        self.username_processor = username_processor
        self.after = after
        self.before = before
        self.path_repo = self.vcs_parser.get_remote_path()


    def get_name_map(self):
        # TODO: Remove this method or refactor it

        self.vcs_parser.parse_log(after=self.after,
                          before=self.before)

        self.access_parser.parse_log(after=self.after,
                                     before=self.before,
                                     path_repo=self.path_repo)


        active_users = []
        active_users += self.access_parser.get_active_users()
        active_users += [self.username_processor.humanname_to_username(n) for n in self.vcs_parser.get_active_users()]

        ret = {}

        for username in active_users:
            ret[username] = self.username_processor.username_to_humanname(username)

        return ret


    def write(self, file_mod, file_usr, file_partition):
        self.vcs_parser.parse_log(after=self.after,
                                  before=self.before)

        self.access_parser.parse_log(after=self.after,
                                     before=self.before,
                                     path_repo=self.path_repo)

        self.write_access_reports(file_mod, file_usr, file_partition)



    def _get_raw_data(self,
                      clone_thr: int = 1024,
                      clone_exp: bool = False) -> tuple:

        oldest_cmt = tuple(self.vcs_parser.get_events_after(self.after))[0]
        oldest_cmt_ts = oldest_cmt[1]

        active_users = []
        active_users += self.access_parser.get_active_users()
        active_users += [self.username_processor.humanname_to_username(n) for n in self.vcs_parser.get_active_users()]

        user_acts = {}

        # 0:  current action
        # -1: previous action
        for user in set(active_users):
            user_acts[user] = {
                0: {},
                -1: {},
            }

        actn_read = int(Action.read)
        actn_fail_read = int(Action.failread)
        actn_upd = int(Action.update)
        actn_fail_upd = int(Action.failupdate)

        # Yield all read access events before the first commit
        for (acc_user,
             acc_ts,
             acc_actn,
             acc_bc) in self.access_parser.get_events_between(self.after,
                                                              self.before):

            if acc_actn not in user_acts[acc_user][0]:
                user_acts[acc_user][0][acc_actn] = 0

            if acc_actn not in user_acts[acc_user][-1]:
                user_acts[acc_user][-1][acc_actn] = 0

            # TODO: or failed to read / update?
            if acc_ts <= oldest_cmt_ts or acc_actn in (actn_fail_read,
                                                       actn_fail_upd):
                yield (acc_actn,
                       acc_user,
                       acc_ts,
                       None,
                       None,
                       None,
                       None,
                       None,
                       None)
            else:

                if user_acts[acc_user][0][acc_actn] > 0:
                    user_acts[acc_user][-1][acc_actn] = \
                        user_acts[acc_user][0][acc_actn]
                user_acts[acc_user][0][acc_actn] = acc_ts

                _after = max(self.after, user_acts[acc_user][-1][acc_actn])
                _before = min(self.before, acc_ts)

                # if user John reads then report all commits that have been
                # writeen by all other users except X after the previous read
                # of John and before the current one

                if acc_actn == actn_upd:
                    xor_operand = False
                elif acc_actn == actn_read:
                    xor_operand = True
                else:
                    continue

                for (cmt_ish,
                     cmt_ts,
                     cmt_user,
                     cmt_event,
                     cmt_pcnt,
                     cmt_modfile,
                     cmt_tgtfile) in self.vcs_parser.get_events_between(_after,
                                                                        _before):

                    cmt_username = self.username_processor.humanname_to_username(cmt_user)

                    if (cmt_username == acc_user) ^ xor_operand:
                        yield (acc_actn,
                               acc_user,
                               acc_ts,
                               cmt_event,
                               cmt_ts,
                               cmt_pcnt,
                               cmt_ish,
                               cmt_modfile,
                               cmt_tgtfile)


    def _prep_rows(self):
        for (event,
             uname,
             iots,
             _cmt_event,
             cmt_ts,
             _pcnt,
             _ish,
             _modfile,
             _tgtfile) in self._get_raw_data():

            if iots is not None:
                iotime = Util.ts_to_report_date(iots)
            else:
                iotime = STR_NA

            if cmt_ts is not None:
                cmt_time = Util.ts_to_report_date(cmt_ts)
            else:
                cmt_time = STR_NA


            pcnt = STR_DASH if _pcnt is None else _pcnt

            ish = STR_NA if _ish is None else _ish

            cmt_event = STR_NA if _cmt_event is None else _cmt_event

            tgtfile = STR_EMP if _tgtfile is None else _tgtfile

            modfile = STR_DASH if _modfile is None else _modfile

            # username_processor

            hname = self.username_processor.username_to_humanname(uname)
         
            yield dict(zip(FLD_REPORT, (uname,
                                        hname,
                                        event,
                                        iotime,
                                        cmt_event,
                                        cmt_time,
                                        pcnt,
                                        ish,
                                        modfile,
                                        tgtfile)
                          )
                      )


    @CLI.with_progress("Generating source code access report...",
    "A total of {} lines written",
    int)
    def write_access_reports(self, file_mod, file_usr, file_partition):
        ctr = 0
        dict_rpt_usr = {}
    
        with open(file_mod, 'wb') as fd_mod:
            for rpt_row in self._prep_rows():

                fd_mod.write(FMT_MODRPT.format(**rpt_row).encode(ENCODING))
                ctr += 1

                uname = rpt_row['uname']
                if uname not in dict_rpt_usr:
                    hname = rpt_row['hname']
                    _usr_tmp = dict_rpt_usr[uname] = io.BytesIO()
                    _usr_tmp.write('\r\n\r\n'.encode(ENCODING))
                    _usr_tmp.write(f'{uname} ({hname}):'.encode(ENCODING))
                    _usr_tmp.write('\r\n\r\n'.encode(ENCODING))

                line = FMT_USRRPT.format(**rpt_row)
                dict_rpt_usr[uname].write(line.encode(ENCODING))
                ctr += 1

        try:
            # Concatenating all user report files to single file
            with open(file_usr, 'wb') as fd_usr:
                for usrfname in dict_rpt_usr.values():
                    usrfname.seek(0)
                    fd_usr.write(usrfname.read())
                    usrfname.close()
        finally:
            for usrfname in dict_rpt_usr.values():
                usrfname.close()

        return ctr



def main():

    desc = '! TODO: Description'
    epilogue = '! TODO: Epilogue'

    path_parent = '.'

    path_git_repo = '/development/users/xillbur/src_audit'

    path_access_log = './ssh_access.log'

    
    ts_now = Util.ts_now()
    ts_today_eod = Util.ts_to_day_end(ts_now)
    ts_today_bod = Util.ts_to_day_beginning(ts_now)

    arg_parser = ArgumentParser(description=desc, epilog=epilogue)
    arg_parser.add_argument('--after', help="After", dest='after', default='epoch', action='store')
    arg_parser.add_argument('--before', help="Before", dest='before', default='today', action='store')
    arg_parser.add_argument('--date', help="Before", dest='date', action='store')

    parsed_args = arg_parser.parse_args()

    if parsed_args.after.lower() == 'epoch':
        _after = Util.ts_to_git_date(0)
    else:
        _after = parsed_args.after
        
    if parsed_args.before.lower() in ('today', 'now'):
        _before = Util.ts_to_git_date(ts_today_eod)
    else:
        _before = parsed_args.before

    if parsed_args.date is not None:
        if parsed_args.before.lower() == 'today':
            _before = Util.ts_to_git_date(ts_today_eod)
            _after = Util.ts_to_git_date(ts_today_bod)


    try:
        after = max(Util.date_to_ts(_after), 0)
        before = max(Util.date_to_ts(_before), 0)

        if after > before:
            raise ValueError("The \'after\' is later than the \'before\' date")
        elif after > ts_now:
            raise ValueError("The \'after\' date is later than the current time")
        elif before > ts_today_eod:
            raise ValueError("The \'before\' date is later than end of the current day")
    except ValueError as ex:
        CLI.errmsg(ex)
        sys.exit(os.EX_USAGE)


    if after == 0:
        str_after = 'the beginning of times'
    elif after == ts_today_bod:
        str_after = "today's BOD"
    else:
        str_after = Util.ts_to_git_date(after)

    if before == ts_today_eod:
        str_before = "today's EOD"
    else:
        str_before = Util.ts_to_git_date(before)

  

    file_mod = Util.get_report_file_path(parent=STR_PERIOD,
                                         prefix=STR_MODULE,
                                         after=after,
                                         before=before)

    file_usr = Util.get_report_file_path(parent=STR_PERIOD,
                                         prefix=STR_USER,
                                         after=after,
                                         before=before)

    file_partition = Util.get_report_file_path(parent=STR_PERIOD,
                                               prefix=STR_USER)

    try:
        for _dir in (path_git_repo, path_parent):
            if not os.path.isdir(_dir):
                raise OSError(errno.ENOTDIR,
                              os.strerror(errno.ENOTDIR),
                              _dir)

        if not os.path.isfile(path_access_log):
            raise OSError(errno.ENOENT,
                          os.strerror(errno.ENOENT),
                          path_access_log)

        for _file in (file_mod, file_usr, file_partition):
            if os.path.exists(_file):
                raise OSError(errno.EEXIST,
                              os.strerror(errno.EEXIST),
                              _file)

    except OSError as ex:
        CLI.errmsg(f'{ex.filename}: {ex.strerror}')
        sys.exit(os.EX_OSFILE)                                      


    git_log_parser = GitRepoDataParser(path_git_repo)
    access_log_parser = PhabricatorAccessLogParser(path_access_log)

    wd = ['John Doe', 'Jane Doe']
    sc = UsernameProcessor(wd)

    au = AuditReportGenerator(git_log_parser,
                              access_log_parser,
                              sc,
                              after=after,
                              before=before)

    print(json.dumps(au.get_name_map(), indent=4))

    sys.exit(1)


    au.write(file_mod, file_usr, file_partition)




def mean(numbers: list) -> float:
    return float(sum(numbers)) / max(len(numbers), 1)

# def main():
#     CLI.infomsg('Total time elapsed, sec: %.2f\n' % mean(Timer('test()', setup='from __main__ import test').repeat(1, 1)))
#     CLI.infomsg('Peak RSS, MB: %.2f (self: %.2f, children: %.2f)\n' % Util.get_peak_rss())

if __name__ == '__main__':
    main()

# EOF
