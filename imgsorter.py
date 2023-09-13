#!/usr/bin/env python3

"""
Media cataloguer, catalogues media files (images, videos) according to the
the files' creation or modification date specified in their metadata.
"""

__author__ = "measure43"
__version__ = "0.1"
__license__ = "MIT"

import argparse
import errno
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import time

from collections.abc import Iterable
from datetime import datetime
from datetime import timedelta
from math import floor, log10
from multiprocessing import Pool
from pathlib import Path
from timeit import default_timer as timer
from typing import Union


# Ok so there's at least five different ways to read EXIF metadata in Python
# and FUCKING NONE OF THEM is better than the other.

# Exiv2 is the fastest
# Exiftool is the most precise, but its just a little bit faster than Wand
# which is the slowest
# Never seen pil and exifreed being used in the current configuration

CFG_DEFAULT = {
    "readers": {
        "exiv2": {
            "name": "Exiv2/pyexiv2",
            "url": ["https://exiv2.org/", "https://pypi.org/project/py3exiv2"],
            "fld": [
                "Exif.Photo.DateTimeOriginal",
                "Exif.Photo.DateTimeDigitized",
                "Exif.GPSInfo.GPSDateStamp",
                "Exif.GPSInfo.GPSDate",
                "Exif.Image.DateTime",
                "Exif.Image.DateTimeOriginal",
                "Exif.Image.DateTimeDigitalized",
                "Iptc.Application2.DateCreated",
                "Iptc.Application2.DigitizationDate",
                "Xmp.xmp.CreateDate",
                "Xmp.exif.DateTimeOriginal",
                "Xmp.exif.DateTimeDigitized",
                "Xmp.video.MediaCreateDate",
                "Xmp.video.DateUTC",
                "Xmp.video.MediaModifyDate",
                "Xmp.video.TrackCreateDate",
                "Xmp.video.TrackModifyDate",
                "Xmp.audio.MediaCreateDate",
                "Xmp.audio.MediaModifyDate",
                "Xmp.photoshop.DateCreated",
                "Xmp.xmp.ModifyDate",
            ],
        },
        "exiftool": {
            "name": "exiftool/PyExifTool",
            "url": ["https://pypi.org/project/PyExifTool"],
            "fld": [
                "EXIF:DateTime",
                "EXIF:GPSDateStamp",
                "EXIF:GPSDate",
                "EXIF:DateTimeOriginal",
                "EXIF:DateTimeDigitized",
                "GPS:GPSDateStamp",
                "GPS:GPSDate",
                "XMP:MediaCreateDate",
                "XMP:DateUTC",
                "XMP:MediaModifyDate",
                "IPTC:DigitizationDate",
                "IPTC:DateCreated",
                "QuickTime:MediaCreateDate",
                "QuickTime:MediaModifyDate",
                "QuickTime:TrackCreateDate",
                "QuickTime:TrackModifyDate",
                "Composite:SubSecCreateDate",
                "Composite:SubSecDateTimeOriginal",
                "Composite:SubSecModifyDate",
            ],
        },
        "pil": {
            "name": "Pillow/PIL",
            "url": ["https://pypi.org/project/Pillow"],
            "fld": [
                "DateTime",
                "GPSDateStamp",
                "GPSDate",
                "DateTimeOriginal",
                "DateTimeDigitized",
            ],
        },
        "exifread": {
            "name": "ExifRead",
            "url": ["https://pypi.org/project/ExifRead"],
            "fld": [
                "EXIF DateTime",
                "GPS GPSDateStamp",
                "GPS GPSDate",
                "EXIF DateTimeOriginal",
                "EXIF DateTimeDigitized",
            ],
        },
        "wand": {
            "name": "Wand/ImageMagick",
            "url": ["https://pypi.org/project/Wand"],
            "ign_ext": [
                "avi",
                "m4v",
                "mov",
                "mp4",
                "ogv",
                "vob",
                "webm",
                "wmv",
                "xvid",
            ],
            "fld": [
                "DateTime",
                "GPSDateStamp",
                "GPSDate",
                "DateTimeOriginal",
                "DateTimeDigitized",
            ],
        },
    },
    "ext": [
        "avi",
        "cr2",
        "cr3",
        "crw",
        "hdr",
        "heic",
        "heif",
        "jfif",
        "jpeg",
        "jpf",
        "jpg",
        "m4v",
        "mkv",
        "mov",
        "mp4",
        "ogg",
        "ogv",
        "png",
        "psd",
        "raw",
        "tga",
        "tif",
        "tiff",
        "vob",
        "wav",
        "webm",
        "wma",
        "wmv",
        "xvid",
    ],
    "priority": ["exiv2", "exiftool", "pil", "exifread", "wand"],
}

DISABLED_METHODS = []

try:
    # pyexiv2 (py3exiv2) depends on exiv2 0.27.6 or later

    import pyexiv2
except ImportError as EX:
    DISABLED_METHODS.append("exiv2")

try:
    # exiftool depends on exiftool command line utility
    from exiftool import ExifToolHelper
    from exiftool.exceptions import ExifToolExecuteError
except ImportError as EX:
    DISABLED_METHODS.append("exiftool")

try:
    from PIL import Image as PillowImage
    from PIL import ExifTags, UnidentifiedImageError
except ImportError as EX:
    DISABLED_METHODS.append("pil")

try:
    import exifread
except ImportError as EX:
    DISABLED_METHODS.append("exifread")

try:
    # wand (Wand) depends on ImageMagick and ffmpeg

    from wand.image import Image as WandImage
except ImportError as EX:
    DISABLED_METHODS.append("wand")


class FileOpError(OSError):
    """Generic file operation error."""

    def __init__(
        self,
        msg: str = None,
        _errno: int = None,
        file_a: Union[str, Path] = None,
        file_b: Union[str, Path] = None,
    ):
        self.msg = msg

        if all(arg is None for arg in (_errno, file_a, file_b)):
            self._strerror = None

            super().__init__()
        else:
            self._strerror = os.strerror(_errno)

            self.files = [None if x is None else str(x) for x in (file_a, file_b)]

            super().__init__(_errno, self._strerror, self.files[0], None, self.files[1])

    @property
    def errno(self):
        """Return the errno if there's any."""

        return super().errno

    @property
    def strerror(self):
        """Return a string representation of the errno if there's any."""

        return self._strerror

    def __str__(self):
        """String representation."""

        ret = str()

        l_files = [repr(x) for x in self.files if x is not None]

        if self.msg is not None:
            ret = self.msg

        if ret:
            ret += ": "

        if self._strerror is not None:
            ret += super().__str__()
        else:
            ret += " -> ".join(l_files)

        return ret


class CLI:
    """CLI class provides convenience functions that may be used to implement
    Command line interafce"""

    ESC = "\033[{!s}m"

    STAT_PAD = 4

    COLORS = {
        "red": 31,
        "green": 32,
        "yellow": 33,
        "blue": 34,
        "endc": 0,
    }

    # Status
    STAT_FAIL = "FAIL"
    STAT_OK = "OK"
    STAT_UNK = "UNK"
    STAT_WARN = "WARN"
    STAT_PROGR = ">>"
    STR_SPACE = " "
    STR_EMPTY = ""

    FMT_MSG_PREFIX = "[{}] : "

    STR_ELIIPSIS = "[...]"

    STATUS = {
        STAT_OK: "green",
        STAT_FAIL: "red",
        STAT_UNK: "blue",
        STAT_PROGR: "blue",
        STAT_WARN: "yellow",
    }

    MSG_MAX_LEN = 0.9

    @classmethod
    def colorize(cls, string: str, clr: str) -> str:
        """Return an ANSI-colorized string."""

        return cls.decorate(string, cls.COLORS[clr])

    @classmethod
    def _msg(cls, msg: str, prefix: str, clr: str) -> str:
        ret = cls.FMT_MSG_PREFIX.format(cls.colorize(prefix, clr)) + str(msg)

        msglen = int(cls.MSG_MAX_LEN * shutil.get_terminal_size().columns)

        if len(ret) > msglen:
            ret = ret[:msglen] + cls.STR_ELIIPSIS

        return ret.ljust(msglen)

    @classmethod
    def decorate(cls, string: str, *style) -> str:
        """Return an ANSI-decorated string. Note that the length of resulting
        string equals string length plus the length of colour escape
        sequence plus the length of `ENDC` escape sequence.
        """

        esc = [cls.ESC.format(s) for s in style if s is not None]

        _style = cls.STR_EMPTY.join(esc)

        endc = cls.ESC.format(cls.COLORS["endc"])

        return f"{_style}{string}{endc}"

    @classmethod
    def infomsg(cls, msg: str, end: str = "\n"):
        """Print an information message."""
        print(cls._msg(msg, "info", "blue"), end=end)

    @classmethod
    def errmsg(cls, msg: str, end: str = "\n"):
        """Print an error message."""
        print(cls._msg(msg, "error", "red"), end=end, file=sys.stderr)


def merge_dict(bottom: dict, top: dict) -> dict:
    """Merge two dictionalies by recursively updating a copy of `bottom` with
    the values from `top`.
    """

    ret = {}

    for _tmp in (bottom, top):
        for key, value in _tmp.items():
            if isinstance(value, dict):
                if key not in ret:
                    ret[key] = value
                else:
                    ret[key] = merge_dict(ret[key], value)
            else:
                ret[key] = _tmp[key]
    return ret


class MDCatalog:
    """Copies image and video files from one place to another cataloguing them
    at the destination using the metadata (EXIF, XMP, IPTC) of the files
    being copied.

    Uses `py3exiv2`, `exiftool`, `PIL`, `exifread` and `Wand` in the order
    specified in the configuration.
    """

    # Size of chunks to read files in. Used only when calculating checksums.
    CHUNK_SZ = 32768

    # There's no way to determine the CPU affinity or the number of physical
    # CPUs with Python standard library in macOS. To reduce an already large
    # number of dependencies, a factor of the total number of available CPUs
    # is used. Setting it to, e.g. 3 / 4 (0.75) on a 12-CPU system will limit
    # the number of processes in the pool to 9.
    NPROC_FACTOR = 3 / 4

    # Minimum number of processes in the pool. The acutual number of processes
    # is a total number of CPUs multiplied by `NPROC_FACTOR', or `NPROC_MIN`
    # whichever is larger, or a total number of files to read metadata from,
    # if it is smaller than the number of CPUs, e.g., if the `NPCROC_FACTOR'
    # is 3 / 4 on a 4-CPU system and there are five files to be processed then
    # the number of processes in the pool is 3, if there are two files the pool
    # size is 2, if there's only one file, the pool size is still 2.
    NPROC_MIN = 2

    # HFS Epoch offset, difference between 01-01-1904 and 01-01-1970.
    # HFS timestamps are used in files created with certain Apple software.
    HFS_EPOCH_OFFSET = 2082844800

    # Regular expression using which the date, as it is read from the
    # corresponding metadata field, is parsed.
    DATE_REGEX = (
        r"\[*(\d{1,4})[-:./](\d{1,2})[-:./](\d{1,4})\]*"
        r"[T\s+]*(\d{1,2})*[-:.]*(\d{1,2})*[-:.]*(\d{1,2})*[-:.]*"
    )

    # Cutoff year, years in two-digit notation before this year will be read
    # as if they are in the 21th century, 20th otherwise.
    # Can be equal or more than the current year.
    YEAR_CUTOFF = 2036

    # Used as a name of a directory, that contains uncatalogized files
    STR_UNCAT = "_uncatalogized"

    # Duplicates list file name
    STR_DUP_FN = "DUPLICATES.txt"

    @classmethod
    def __cksum(cls, hashobj: hashlib._hashlib.HASH, fpath: Path) -> str:
        """Calculate the checksum of the specified file using the specified
        algorythm.
        """

        with fpath.open(mode="rb") as fhdl:
            while True:
                data = fhdl.read(cls.CHUNK_SZ)
                if not data:
                    break
                hashobj.update(data)

        return hashobj.hexdigest()

    @classmethod
    def _sha1sum(cls, fpath: Path) -> str:
        """Calculate the SHA1 checksum of the specified file."""

        return cls.__cksum(hashlib.sha1(), fpath)

    @classmethod
    def copy(cls, src: Path, dst: Path, cksum=None):
        """Copy a file then verify the destination file's checksum."""

        if dst.exists() and src.samefile(dst):
            raise FileOpError("Same file", errno.EEXIST, src, dst)

        if cksum is None:
            src_cksum = cls._sha1sum(src)
        else:
            src_cksum = cksum

        if dst.exists():
            raise FileOpError("Destination file exists", errno.EEXIST, dst)

        dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(src, dst)

        dst_cksum = cls._sha1sum(dst)

        if src_cksum != dst_cksum:
            raise FileOpError("Destination file corrupted", errno.ENOENT, dst)

    @staticmethod
    def _walk_files(dpath: Path) -> Path:
        """Return an iterator over all files in the specified directory."""

        if dpath.is_dir():
            for root, _, files in os.walk(dpath):
                for file in files:
                    fpath = Path(root, file)

                    if fpath.is_file():
                        yield fpath

    @staticmethod
    def _dttofpath(dtime: datetime, suf: str = None, ext: str = None) -> str:
        """Create a relative file path from date time, suffix and extension."""

        subdir = Path(f"{dtime.year:>04}", f"{dtime.month:>02}")

        fname = (
            f"{dtime.year:>04}"
            f"{dtime.month:>02}"
            f"{dtime.day:>02}"
            f"{dtime.hour:>02}"
            f"{dtime.minute:>02}"
        )

        if suf is not None:
            fname += "_" + suf

        if ext is not None:
            fname += "." + ext.lstrip(".")

        return subdir.joinpath(fname)

    def __init__(self, src: Union[str, Path], dst: Union[str, Path], cfg: dict):
        _src = Path(src).resolve()
        _dst = Path(dst).resolve()

        ex_args = None

        if not _src.exists():
            ex_args = ("Source location does not exist", errno.ENOENT, _src)
        elif _dst.is_symlink():
            ex_args = (
                "Destination path points to a symbolic link",
                errno.EEXIST,
                _src,
                _dst,
            )
        elif _src.samefile(_dst):
            ex_args = (
                "Source and destination paths are the same",
                errno.EEXIST,
                _src,
                _dst,
            )
        elif _src.is_relative_to(_dst):
            ex_args = (
                "Source path is in the destination path",
                errno.EEXIST,
                _src,
                _dst,
            )
        elif _dst.is_relative_to(_src):
            ex_args = (
                "Destination path is in the source path",
                errno.EEXIST,
                _src,
                _dst,
            )

        if ex_args is not None:
            raise FileOpError(*ex_args)

        self.src = _src
        self.dst = _dst

        self.funcs = []

        _ext = set(cfg["ext"])

        for f_name in [fn for fn in cfg["priority"] if fn in cfg["readers"]]:
            if "ign_ext" in cfg["readers"][f_name]:
                f_ext = _ext ^ set(cfg["readers"][f_name]["ign_ext"])
            else:
                f_ext = _ext

            self.funcs.append((f_name, f_ext, cfg["readers"][f_name]["fld"]))

        self.pat_dtime = re.compile(MDCatalog.DATE_REGEX, re.IGNORECASE)

    def _as_datetime(self, date: Union[str, int]) -> datetime:
        """Convert the specified value to a `datetime.datetime` object. The
        specified value can be a date and (or) time string of one of the
        popular date and time formats, or a string or integer representing
        a Unix timestamp.
        """

        ret = None

        if date is not None:
            date = str(date).strip()

            if date.isnumeric():
                ts_date = int(date)

                if ts_date > MDCatalog.HFS_EPOCH_OFFSET:
                    # HFS timestamp, this will work until the year 2036
                    ts_unix = ts_date - MDCatalog.HFS_EPOCH_OFFSET

                    if ts_unix < time.time():
                        ret = datetime.fromtimestamp(ts_unix)

                else:
                    ret = datetime.fromtimestamp(date)

            else:
                match = self.pat_dtime.match(date)

                if match is not None:
                    t_dt = tuple(int(x or 0) for x in match.groups())

                    year, month, day, hour, minute, second = t_dt

                    dt_max = datetime.max

                    # Handle YYYY-MM-DD and DD-MM-YYYY date formats
                    if day == 0 or day > dt_max.day:
                        # Swap the day for year
                        day, year = year, day

                    # The first year of the cutoff year century
                    # _year = year // 10 ** (int(log10(year)) - 1) * 100
                    base_year = floor(MDCatalog.YEAR_CUTOFF / 100) * 100

                    # Got a two-digit year.
                    if year > 0 and int(log10(year)) <= 1:
                        if year > MDCatalog.YEAR_CUTOFF % 100:
                            base_year = base_year - 100

                        year += base_year
                    elif year == 0 and month != 0 and day != 0:
                        # Year 2000 written as 00
                        year = base_year

                    # Month is greater than 12; date in YYYY-MM-DD format
                    if month > dt_max.month and day <= dt_max.month:
                        month, day = day, month

                    # Hour is greater than 23 or 60 time in 24-hour format
                    if hour > dt_max.hour:
                        hour = 0

                    ret = datetime(year, month, day, hour, minute, second)
        return ret

    def get_date_pil(self, fpath: Path, flds: list) -> datetime:
        """Return creation date from metadata of specified file using PIL."""

        ret = None
        try:
            with PillowImage.open(str(fpath)) as img:
                exif = img.getexif()
                if exif is not None and exif:
                    exif_ids = [
                        k
                        for k, v in exif.items()
                        if k in ExifTags.TAGS and ExifTags.TAGS[k] in flds
                    ]

                    for exifkey in exif_ids:
                        if exifkey in exif:
                            ret = self._as_datetime(exif[exifkey])

                            if ret is not None:
                                break

        except (UnidentifiedImageError, OSError) as ex:
            raise FileOpError() from ex

        return ret

    def get_date_exiv2(self, fpath: Path, flds: list) -> datetime:
        """Return creation date from metadata of specified file using Exiv2
        (pyexiv2/py3exiv2).
        """

        ret = None

        try:
            metadata = pyexiv2.ImageMetadata(str(fpath))
            metadata.read()

            for key in flds:
                if key in metadata:
                    ret = self._as_datetime(metadata[key].raw_value)
                    if ret is not None:
                        break

        except (TypeError, OverflowError, OSError) as ex:
            raise FileOpError(None, errno.ENODATA, fpath) from ex

        return ret

    def get_date_exiftool(self, fpath: Path, flds: list) -> datetime:
        """Return creation date from metadata of specified file using
        Exiftool.
        """

        ret = None

        with ExifToolHelper() as hlp:
            try:
                for md_dict in hlp.get_tags(str(fpath), tags=flds):
                    for date in md_dict.values():
                        ret = self._as_datetime(date)
                        if ret is not None:
                            break
            except (ExifToolExecuteError, OSError) as ex:
                raise FileOpError(None, errno.ENODATA, fpath) from ex

        return ret

    def get_date_exifread(self, fpath: Path, flds: list) -> datetime:
        """Return creation date from metadata of specified file using
        Exifread.
        """

        ret = None

        try:
            with fpath.open(mode="rb") as fhdl:
                exif = exifread.process_file(fhdl)
                if exif is not None and exif:
                    for exifkey in flds:
                        if exifkey in exif:
                            # exifread.process_file returns a dictionary of
                            # idTag objects, not strings
                            ret = self._as_datetime(exif[exifkey])

                            if ret is not None:
                                break

        except (exifread.heic.NoParser, OSError) as ex:
            raise FileOpError(None, errno.ENODATA, fpath) from ex

        return ret

    def get_date_wand(self, fpath: Path, flds: list) -> datetime:
        """Return creation date from metadata of specified file using Wand
        (ImageMagick).
        """

        ret = None

        try:
            with WandImage(filename=str(fpath)) as img:
                for key, value in img.metadata.items():
                    for exifkey in flds:
                        if key == f"exif:{exifkey}":
                            ret = self._as_datetime(value)

                            if ret is not None:
                                break

        except Exception as ex:
            raise FileOpError(None, errno.ENODATA, fpath) from ex

        return ret

    def _get_date(self, fpath: Path) -> datetime:
        """Return creation date from metadata of specified file using all
        available methods in the order specified in the cofiguration.
        """

        ret = None

        ext = fpath.suffix.lower().lstrip(".")

        for f_name, f_ext, f_flds in self.funcs:
            if ext in f_ext:
                try:
                    f_ref = getattr(self, f"get_date_{f_name}", None)

                    if f_ref is not None:
                        ret = f_ref(fpath, f_flds)
                except FileOpError as ex:
                    logging.debug(
                        "%s: Failed to read date with '%s': %s",
                        fpath,
                        f_name,
                        ex,
                    )

                if ret is not None:
                    break

        return ret

    def _f_info(self, fpath: Path) -> tuple[Path, str, datetime]:
        """Return a file info tuple of file path, SHA1 checksum and cretion
        date.
        """

        return (fpath, MDCatalog._sha1sum(fpath), self._get_date(fpath))

    def search(self) -> list[Path]:
        """Return the list of all files in the source directory specified
        during initialization.
        """

        CLI.infomsg("Looking for files, please wait...", end="\r")

        ret = list(MDCatalog._walk_files(self.src))

        CLI.infomsg(f"Found {len(ret)} files.")

        return ret

    @staticmethod
    def _init_worker():
        """Initialize the worker process."""

        logging.basicConfig(level=logging.CRITICAL)

    def analyze(self, files: Iterable) -> tuple[dict]:
        """Return a tuple of catalogued, uncatalogued and duplicate files in
        the specified list of files paths.
        """

        CLI.infomsg("Analyzing files, please wait...", end="\r")

        len_files = len(files)
        cpu_count = round(os.cpu_count() * MDCatalog.NPROC_FACTOR)

        nproc = max(MDCatalog.NPROC_MIN, cpu_count)

        if len_files < nproc:
            nproc = len_files

        store = {}
        dup = {}

        with Pool(processes=nproc, initializer=MDCatalog._init_worker) as pool:
            for fpath, cksum, date in pool.imap_unordered(self._f_info, files):
                if cksum in store:
                    # Duplicate

                    if cksum not in dup:
                        dup[cksum] = []

                    dup[cksum].append(fpath)
                else:
                    store[cksum] = (fpath, date)

        CLI.infomsg(f"{len(store)} files OK, {len(dup)} duplicates.")

        return (store, dup)

    def transfer(self, store: dict, dup: dict = None) -> tuple[int]:
        """Transfre (copy) files to the destination directory."""

        if self.dst.is_dir():
            dup_lns = []

            cnt = 0

            for cksum, (path, dtime) in store.items():
                if dtime is None:
                    rel_part = path.relative_to(self.src).parts
                    rel_path = Path(MDCatalog.STR_UNCAT, *rel_part)
                else:
                    rel_path = MDCatalog._dttofpath(dtime, cksum[0:8], path.suffix)

                dst_path = self.dst.joinpath(rel_path)

                MDCatalog.copy(path, dst_path)

                cnt += 1

                CLI.infomsg(f"Transferred {cnt} files.", end="\r")

                if dup is not None and cksum in dup:
                    dup_lns.append(f"{cksum}: '{path}' -> '{dst_path}'")

                    for num, name in enumerate(dup[cksum]):
                        dup_lns.append(f" + ({num}) '{name}'")

                    dup_lns.append("")

                    del dup[cksum]

            if dup_lns:
                fpath = MDCatalog.STR_DUP_FN
                with self.dst.joinpath(fpath).open("w", encoding="utf-8") as fhdl:
                    fhdl.write("\n".join(dup_lns))

            if dup:
                raise RuntimeError("unprocessed duplicates left")

            CLI.infomsg(f"Successfully transferred {cnt} files.")

    def run(self):
        """Make the magic(k) happen"""

        files = self.search()

        store, dup = self.analyze(files)

        self.transfer(store, dup)


if __name__ == "__main__":
    logging.basicConfig(level=logging.CRITICAL)

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--from", help="Source directory", dest="src", type=Path, required=True
    )

    parser.add_argument(
        "--to",
        help="Destination directory",
        dest="dest",
        type=Path,
        required=True,
    )

    parser.add_argument("--config", help="Configuration file path", type=Path)

    parser.add_argument(
        "--debug-raise",
        help="Raise exceptions instead of printing error messages",
        action="store_true",
    )

    parser.add_argument("--disable-methods", nargs="+", default=[])

    opts = parser.parse_args()

    config = {}

    if opts.config:
        with opts.config.open("r") as _fhdl:
            _data = json.load(_fhdl)

            config = merge_dict(CFG_DEFAULT, _data)

    if not config:
        config = CFG_DEFAULT

    for dis_method in DISABLED_METHODS + opts.disable_methods:
        if dis_method in config["priority"]:
            config["priority"].remove(dis_method)

    enab = [key for key in config["priority"] if key in config["readers"]]

    CLI.infomsg("Using metadata lookup methods: " + ", ".join(enab))

    try:
        cat = MDCatalog(opts.src, opts.dest, CFG_DEFAULT)

        before = timer()

        cat.run()

        after = timer()

        tdelta = timedelta(seconds=after - before)

        CLI.infomsg(f"Elapsed time is {tdelta}")

    except (FileOpError, OSError, ValueError) as _ex:
        if opts.debug_raise:
            raise

        CLI.errmsg(_ex)
