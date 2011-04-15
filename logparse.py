#!/usr/bin/env python2.5
# Kornilios Kourtis <kkourt@cslab.ece.ntua.gr>

from cStringIO import StringIO
import re

class StopParsing(Exception):
	pass

class MultiFiles(object):
    """
    Use this class to fool LogParser so that it parses mutliple
    files in one pass
    """
    def __init__(self, files_iter, start_msg, end_msg):
        """ create a MultiFiles object:

           files_iter: iterator of multiple files
           start_msg : function to print message when a new file starts
                       (is called with the name of the file as argument)
           end_msg   : similar to start_msg
        """
        self._files_iter = files_iter
        self._start_msg  = start_msg
        self._end_msg    = end_msg
        self._cur_fname  = None
        self._cur_file   = None

    def readline(self): # QUACK, QUACK!
        if self._cur_file is not None:
            ret = self._cur_file.readline()
            if ret != '':
                return ret
            # file ended
            self._cur_file = self._cur_fname = None
            return self._end_msg(self._cur_fname)
        # need to open new file
        try:
            fname = self._files_iter.next()
        except StopIteration:
            return ''
        self._cur_fname = fname
        self._cur_file  = open(fname)
        ret = self._start_msg(self._cur_fname)
        return ret

class LogParser(object):
	"""
	LogParser: This class implements a file parser:
	 - The output of the parser is a list of key-value pairs.
	 - The parser is configured by the user using a simple language
	   based on regular expressions.
	 - It presumes an order in the data of the file (it keeps state
	   for only one tuple of key-value pairs at a time)

	The user configures the parser by defining regular expressions and
	a set of commands that are executed when each regex is matched.

	The available commands are:
	 - assign:  assign a value to a key
	 - flush:   output a key-value tuple
	 - clear:   destroy a key
	 - regexes: execute a set of commands when a regex is matched
	 - eval:    evaluate (eval()) the argument
	 - exit:    stop parsing

	The regular expressions and their commands are defined as:
	/REGEX0/
		command0
		command1
		...

	/REGEX1/
		command0
		command1
		...

	Assignment ('key=expression'):
	  - key string representing they key assigned
	  - expression will be passed to an eval() function.
	  In the expression the following variables are available:
	  _gX (_g1,_g2) correspond to the regex groups
	  __match_obj   corresonds to the match object
	  __finpt_obj   corresponds to the current file object
	  __globs_obj   corresponds to the actual globs __init__() argument
	                This is intented for performing updates
	  contents of globs __init__() argument (this is a copy)

	Flush ('flush'): output key,value pairs if any

	Clear ('clear [key0 key1]'):
	  - Clear contents of keys (no arguments => all keys are cleared)

	Regular Expression: similar to regex patterns

	Example:

	>>> conf_data = '''
	... /^(\w+) (\w+)$/
	...     fname = _g1
	...     lname = _g2
	...     /^(Helen|Maria).*$/
	...         message = "Hello " + _g1
	...     flush
	...     clear message
	... '''
	>>> indata = '''
	... Helen Smith
	... Nick Papadopoulos
	... Jane Doe
	... '''
	>>> lp = LogParser(conf_data=conf_data)
	>>> lp.go(indata)
	>>> lp.data
	[{'lname': 'Smith', 'message': 'Hello Helen', 'fname': 'Helen'}, {'lname': 'Papadopoulos', 'fname': 'Nick'}, {'lname': 'Doe', 'fname': 'Jane'}]

	Note that regular expressions need to match the whole line
	"""
	re_regex = re.compile(r'^/(.*)/$')
	re_regex_ws = re.compile(r'^\s+/(.*)/$')
	re_initial_ws = re.compile(r'^(\s+)')
	re_ws = re.compile(r'^\s+$')
	re_assign = re.compile(r'^\s+(\w\S*)\s*=\s*([^#\n]+).*$')
	re_flush = re.compile(r'^\s+flush\s*$')
	re_clear = re.compile(r'^\s+clear((?:\s+\w+){0,})\s*$')
	re_eval = re.compile(r'^\s+eval\s+(.*)$')
	re_exit = re.compile(r'^\s+exit\s*$')

	def __init__(self, conf_data, debug=False, globs=None, eof_flush=False):
		""" Create a LogParser instance.

		conf_data: parser configuration (string or file-like object)
		debug:     print debug messages
		globs:     globals for assign right-term evaluation (see eval())
		eof_flush: flush when encounter an EOF
		"""
		self._debug = debug
		self._globals = globals() if globs is None else globs
		self._rules = []
		self.lterms = set()
		self._init(conf_data)
		self._current_data = {}
		self._eof_flush = eof_flush
		self._f = None
		self.data = []

	def _init(self, conf_data):
		""" intialize parser from conf_data """
		if isinstance(conf_data, str):
			conf_data = StringIO(conf_data)

		re_regex = self.re_regex
		re_ws = self.re_ws
		while True:
			l = conf_data.readline()
			if l == '':
				break
			if l.startswith('#') or (re_ws.match(l) is not None):
				continue

			# match a regular expression
			match = re_regex.match(l)
			if match is not None:
				regex_str =  match.groups()[0]
				regex = self._compile_regex(regex_str)
				commands = self._init_commands(conf_data)
				self._rules.append((regex, commands))
				continue

			raise ValueError, "parse error %s (not a regexp)" % l[:-1]

	def _init_commands(self, conf_data, initial_ws=''):
		""" Intialize commands for a regular expression """
		commands = [] # commands for this regular expression
		re_ws = self.re_ws
		re_regex = self.re_regex_ws
		re_assign = self.re_assign
		re_flush = self.re_flush
		re_clear = self.re_clear
		re_eval = self.re_eval
		re_exit = self.re_exit

		# first line
		pp = conf_data.tell() # previous position
		l = conf_data.readline()
		assert(l.startswith(initial_ws))
		current_ws = self.re_initial_ws.match(l).groups()[0]
		assert(len(current_ws) > len(initial_ws))
		conf_data.seek(pp)

		while True:
			# get next line
			pp = conf_data.tell()
			l = conf_data.readline()
			if l == '':
				break
			if not l.startswith(current_ws):
				# go back
				conf_data.seek(pp)
				break

			# regular expression command, calls _init_commands() recursively
			match = re_regex.match(l)
			if match is not None:
				regex = self._compile_regex(match.groups()[0])
				new_commands = self._init_commands(conf_data, current_ws)
				commands.append(('RE', regex, new_commands))
				continue

			# assignment command
			match = re_assign.match(l)
			if match is not None:
				(lterm, rterm) = match.groups()
				commands.append(('=', lterm, rterm))
				self.lterms.add(lterm)
				continue

			# flush command
			match = re_flush.match(l)
			if match is not None:
				commands.append(('FL',))
				continue

			# clear command
			match = re_clear.match(l)
			if match is not None:
				cl_cmd = [ "CL" ]
				terms, = match.groups()
				if terms:
					cl_cmd.append(terms.split())
				commands.append(cl_cmd)
				continue

			# exit command
			match = re_exit.match(l)
			if match is not None:
				commands.append(('EXIT', ))
				continue

			# eval command
			match = re_eval.match(l)
			if match is not None:
				commands.append(('EVAL', match.groups()[0] ))
				continue

			# Unknown command
			raise ValueError, "parse error <%s> (not a valid command)" % (l[:-1],)

		return commands


	def _compile_regex(self, regex):
		""" wrapper for compiling regular expressions """
		if self._debug:
			print "got regex: %s" % regex
		try:
			regex = re.compile(regex)
		except:
			print "Failed to compile regex '%s'" % regex
			raise
		return regex


	def _execute_commands(self, commands, match):
		""" execute (all) commands for a match """
		for command in commands:
			# flush command
			if command[0] == 'FL':
				if self._debug:
					print 'FLUSH'
				if self._current_data:
					yield dict(self._current_data)
			# clear command
			elif command[0] == 'CL':
				if self._debug:
					print 'CLEAR',
				# no arguments, clear all keys
				if len(command) == 1:
					if self._debug:
						print 'ALL'
					self._current_data.clear()
				else:
					if self._debug:
						print 'TERMS: ', ' '.join(command[1])
					# clear only keys in arguments
					for term in command[1]:
						if term in self._current_data:
							del self._current_data[term]
			# assighment command
			elif command[0] == '=':
				lterm, rterm = command[1:]
				groups = match.groups()
				# set up globs, add  match variables and match object
				globs = dict(self._globals)
				for i in xrange(len(groups)):
					globs['_g%d' % (i+1)] = groups[i]
				globs['__match_obj'] = match
				globs['__finpt_obj'] = self._f
				#globs['__cdata_obj'] = self._current_data

				try:
					rterm = eval(rterm, globs)
				except:
					print "FAILED to evaluate: %s = %s" % (lterm, rterm,)
					raise

				if self._debug:
					print 'ASSIGN ', lterm, '=', rterm, '--'
				self._current_data[lterm] = rterm

			# regular expression command
			elif command[0] == 'RE':
				nregex, ncommands = command[1:]
				nmatch = nregex.match(match.group(0))
				if nmatch is not None:
					rets = self._execute_commands(ncommands, nmatch)
					for ret in rets:
						yield ret

			# eval command
			elif command[0] == 'EVAL':
				if self._debug:
					print 'EVAL '
				groups = match.groups()
				cmd = command[1]
				globs = dict(self._globals)
				for i in xrange(len(groups)):
					globs['_g%d' % (i+1)] = groups[i]
				for k,v in self._current_data.iteritems():
					globs['_%s' % k ] = v
				globs['__match_obj'] = match
				globs['__finpt_obj'] = self._f
				globs['__globs_obj'] = self._globals
				eval(cmd, globs)

			# exit command
			elif command[0] == 'EXIT':
				raise StopParsing

			else:
				raise ValueError, "Unknown command: %s" % command[0]

	def go_iter(self, f):
		""" iterator that parses a file object, and yields the
		    resulting key-value pairs """
		if isinstance(f, str):
			f = StringIO(f)
		self._f = f # this is just used for the __finpt_obj

		if self._debug:
			print 'STARTED PARSING'

		try:
			while True:
				l = f.readline()
				if l == '':
					break
				for pattern, commands in self._rules:
					match = pattern.match(l)
					if match is not None:
						rets = self._execute_commands(commands, match)
						for ret in rets:
							yield ret
		except StopParsing:
			pass

		if self._eof_flush:
			yield dict(self._current_data)
		if self._debug:
			print 'ENDED PARSING'

	def go(self, f):
		""" parses a file object, and put the result in .data """
		self.data = list(self.go_iter(f))

def logparse(fileobj, *args,**kwargs):
	lp = LogParser(*args,**kwargs)
	lp.go(fileobj)
	return lp.data

if __name__ == '__main__':
	import doctest
	doctest.testmod()
