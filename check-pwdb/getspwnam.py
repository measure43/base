#!/usr/bin/env python
from __future__ import print_function
import os
import sys
import spwd
import pwd

if len(sys.argv) < 2:
  print("[ERROR]: No username supplied.")
  sys.exit(255)

req_username = sys.argv[1]

pwd_map = {
  0: ["pw_name", "Login name"],
  1: ["pw_passwd", "Optional encrypted password"],
  2: ["pw_uid", "Numerical user ID"],
  3: ["pw_gid", "Numerical group ID"],
  4: ["pw_gecos", "User name or comment field"],
  5: ["pw_dir", "User home directory"],
  6: ["pw_shell", "User command interpreter"]
}

spwd_map = {
  0: ["sp_nam", "Login name"],
  1: ["sp_pwd", "Encrypted password"],
  2: ["sp_lstchg", "Date of last change"],
  3: ["sp_min", "Minimal number of days between changes"],
  4: ["sp_max", "Maximum number of days between changes"],
  5: ["sp_warn", "Number of days before password expires to warn user about it"],
  6: ["sp_inact", "Number of days after password expires until account is blocked"],
  7: ["sp_expire", "Number of days since 1970-01-01 until account is disabled"],
  8: ["sp_flag", "Reserved"]
}

try:
  shadowpwd = spwd.getspnam(req_username)
except KeyError as err_str:
  shadowpwd = None

try:
  plainpwd = pwd.getpwnam(req_username)
except KeyError as err_str:
  plainpwd = None

fmt_string = "%-2s %-10s %-24s %-38s"

if plainpwd:
  print("\nPlain password database:")
  print(fmt_string % ("#", "Key", "Value", "Description"))
  print(fmt_string % ("-", "---", "-----", "-----------"))
  for pw_entry in pwd_map.keys():
    try:
      print(fmt_string % (pw_entry, pwd_map[pw_entry][0], plainpwd[pw_entry], pwd_map[pw_entry][1]))
    except KeyError as err_str:
        print("* WARNING: Key %s (%s) is absent in password entry structure." % (pw_entry, pwd_map[pw_entry][0]))
else:
  print("\n* ERROR: Entry for %s is not found in plain password database" % req_username)

if shadowpwd:
  print("\nShadow password database:")
  print(fmt_string % ("#", "Key", "Value", "Description"))
  print(fmt_string % ("-", "---", "-----", "-----------"))
  for pw_entry in spwd_map.keys():
    try:
      print(fmt_string % (pw_entry, spwd_map[pw_entry][0], shadowpwd[pw_entry], spwd_map[pw_entry][1]))
    except KeyError as err_str:
      print("* WARNING: Key %s (%s) is absent in password entry structure." % (pw_entry, spwd_map[pw_entry][0]))
else:
  print("\n* ERROR: Entry for %s is not found in shadow password database" % req_username)






