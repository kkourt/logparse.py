#!/usr/bin/env python2.5
# Kornilios Kourtis <kkourt@cslab.ece.ntua.gr>
from logparse import LogParser

"""
This is an example of using the Logparser class for parsing an mbox file.  The
example file is from linux-kernel archives:
http://userweb.kernel.org/~akpm/lkml-mbox-archives/2000-11.bz2

Note that:
|  MESSAGE FORMAT
|       A message encoded in mbox format begins with a From_ line,
|       continues with a series of non-From_ lines, and ends with a
|       blank line.  A From_ line means any line that begins with
|       the characters F, r, o, m, space:
...
|  HOW A MESSAGE IS READ
|       A reader scans through an mbox file looking for From_ lines.
|       Any From_ line marks the beginning of a message.  The reader
|       should not attempt to take advantage of the fact that every
|       From_ line (past the beginning of the file) is preceded by a
|       blank line.
|
|       Once the reader finds a message, it extracts a (possibly
|       corrupted) envelope sender and delivery date out of the
|       From_ line.  It then reads until the next From_ line or end
|       of file, whichever comes first.  It strips off the final
|       blank line and deletes the quoting of >From_ lines and
|       >>From_ lines and so on.  The result is an RFC 822 message.


 - http://www.qmail.org/man/man5/mbox.html

Run with:
 $ python2.5 lk_parse.py 2000-11
"""

mbox_parse = r'''
/^From \S+ .*$/
	flush
	clear patch

/^From: \s*(.*)$/
	from=_g1

/^Date: \s*(.*)$/
	date=_g1

/^Subject: \s*(.*)$/
	/.*\[PATCH\].*/
		patch=True
	subject=_g1
'''


""" Notes
 - We need to clear patch, so it doesn't appear in next result
"""

if __name__ == "__main__":
	from sys import argv

	f = open(argv[1])
	lp = LogParser(mbox_parse, debug=False, globs={}, eof_flush=True)
	for d in lp.go_iter(f):
		print '\t\n'.join( "%-8s : %s" % (i[0], i[1]) for i in d.iteritems() ), "\n"
