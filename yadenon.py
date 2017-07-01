#!/usr/bin/env python

import mock
import serial
import unittest
import threading
import time

class DenonAVR(object):
	def __init__(self, serdev):
		self._ser = serial.serial_for_url(serdev, baudrate=9600,
		    timeout=.5)
		self._power = None
		self._vol = None
		self._volmax = None
		self._speakera = None
		self._speakerb = None
		self._z2mute = None
		self._zm = None
		self._ms = None

	@property
	def ms(self):
		'Surround mode'

		return self._ms

	@property
	def power(self):
		'Power status, True if on'

		return self._power

	@power.setter
	def power(self, arg):
		arg = bool(arg)

		if arg != self._power:
			args = { True: 'ON', False: 'STANDBY' }
			self._sendcmd('PW', args[arg])
			self.process_events(till='PW')
			time.sleep(1)
			self.update()

	@staticmethod
	def _makevolarg(arg):
		arg = int(arg)
		if arg < 0 or arg > 99:
			raise ValueError('Volume out of range.')

		arg -= 1
		arg %= 100

		return '%02d' % arg

	@staticmethod
	def _parsevolarg(arg):
		arg = int(arg)
		if arg < 0 or arg > 99:
			raise ValueError('Volume out of range.')

		arg += 1
		arg %= 100

		return arg

	@property
	def vol(self):
		'Volumn, range 0 through 99'

		return self._vol

	@vol.setter
	def vol(self, arg):
		if arg == self._vol:
			return

		if self._volmax is not None and arg > self._volmax:
			raise ValueError('volume %d, exceeds max: %d' % (arg,
			    self._volmax))
		arg = self._makevolarg(arg)

		time.sleep(1)
		self._sendcmd('MV', arg)
		self.process_events(till='MV')
		self.process_events(till='MV')

	@property
	def volmax(self):
		'Maximum volume supported.'

		return self._volmax

	def proc_PW(self, arg):
		if arg == 'STANDBY':
			self._power = False
		elif arg == 'ON':
			self._power = True
		else:
			raise RuntimeError('unknown PW arg: %s' % `arg`)

	def proc_MU(self, arg):
		if arg == 'ON':
			self._mute = True
		elif arg == 'OFF':
			self._mute = False
		else:
			raise RuntimeError('unknown MU arg: %s' % `arg`)

	def proc_ZM(self, arg):
		if arg == 'ON':
			self._zm = True
		elif arg == 'OFF':
			self._zm = False
		else:
			raise RuntimeError('unknown ZM arg: %s' % `arg`)

	def proc_MV(self, arg):
		if arg[:4] ==  'MAX ':
			self._volmax = self._parsevolarg(arg[4:])
		else:
			self._vol = self._parsevolarg(arg)

	def proc_MS(self, arg):
		self._ms = arg

	def proc_PS(self, arg):
		if arg == 'FRONT A':
			self._speakera = True
			self._speakerb = False
		else:
			raise RuntimeError('unknown PS arg: %s' % `arg`)

	def proc_Z2(self, arg):
		if arg == 'MUOFF':
			self._z2mute = False
		else:
			raise RuntimeError('unknown Z2 arg: %s' % `arg`)

	def _sendcmd(self, cmd, args):
		cmd = '%s%s\r' % (cmd, args)

		print 'scmd:', `cmd`
		self._ser.write(cmd)
		self._ser.flush()

	def _readcmd(self, timo=None):
		'''If timo == 0, and the first read returns the empty string,
		it will return an empty command, otherwise returns a
		command.'''

		cmd = ''

		#while True:
		if timo is not None:
			oldtimo = self._ser.timeout
			self._ser.timeout = timo

		for i in xrange(30):
			c = self._ser.read()
			if (timo == 0 or timo is None) and c == '':
				break

			#print 'r:', `c`, `str(c)`
			if c == '\r':
				break

			cmd += c
		else:
			raise RuntimeError('overrun!')

		if timo is not None:
			self._ser.timeout = oldtimo

		print 'rc:', `cmd`
		return cmd

	def process_events(self, till=None):
		'''Process events until the till command is received, otherwise
		process a single event.'''

		assert till is None or len(till) == 2
		print 'till:', `till`
		while True:
			event = self._readcmd()

			if len(event) >= 2:
				fun = getattr(self, 'proc_%s' % event[:2])
				fun(event[2:])

			if till is None or event[:2] == till:
				return event

	def update(self):
		'''Update the status of the AVR.'''

		self._sendcmd('PW', '?')
		self._sendcmd('MV', '?')
		self.process_events(till='MV')	# first vol
		self.process_events(till='MV')	# second max vol

class TestDenon(unittest.TestCase):
	TEST_DEV = '/dev/tty.usbserial-FTC8DHBJ'

	# comment out to make it easy to restore skip
	@unittest.skip('perf')
	def test_comms(self):
		avr = DenonAVR(self.TEST_DEV)
		self.assertIsNone(avr.power)

		avr.update()

		self.assertIsNotNone(avr.power)
		self.assertIsNotNone(avr.vol)

		avr.power = False

		time.sleep(1)

		avr.power = True

		self.assertTrue(avr.power)

		print 'foostart'

		time.sleep(1)

		avr.update()

		time.sleep(1)

		avr.vol = 0

		self.assertEqual(avr.vol, 0)

		time.sleep(1)

		avr.vol = 5

		avr.update()
		self.assertEqual(avr.vol, 5)

		avr.vol = 50

		avr.update()
		self.assertEqual(avr.vol, 50)

		avr.power = False

		self.assertFalse(avr.power)

		self.assertIsNotNone(avr.volmax)

class TestStaticMethods(unittest.TestCase):
	def test_makevolarg(self):
		self.assertRaises(ValueError, DenonAVR._makevolarg, -1)
		self.assertRaises(ValueError, DenonAVR._makevolarg, 3874)
		self.assertRaises(ValueError, DenonAVR._makevolarg, 100)

		self.assertEqual(DenonAVR._makevolarg(0), '99')
		self.assertEqual(DenonAVR._makevolarg(1), '00')
		self.assertEqual(DenonAVR._makevolarg(99), '98')

	def test_parsevolarg(self):
		self.assertEqual(DenonAVR._parsevolarg('99'), 0)
		self.assertEqual(DenonAVR._parsevolarg('00'), 1)
		self.assertEqual(DenonAVR._parsevolarg('98'), 99)

		self.assertRaises(ValueError, DenonAVR._parsevolarg, '-1')

class TestMethods(unittest.TestCase):
	@mock.patch('serial.serial_for_url')
	def setUp(self, sfu):
		self.avr = DenonAVR('null')

	def test_proc_events(self):
		avr = self.avr

		avr._ser.read.side_effect = 'PWON\r'
		avr.process_events()

		self.assertTrue(avr._ser.read.called)

		avr._ser.read.reset()

		avr._ser.read.side_effect = 'MUON\r' + 'PWON\r'
		avr.process_events(till='PW')

		avr._ser.read.assert_has_calls([ mock.call(), mock.call() ])

	@mock.patch('denon.DenonAVR._sendcmd')
	@mock.patch('denon.DenonAVR.process_events')
	@mock.patch('time.sleep')
	@mock.patch('denon.DenonAVR.update')
	def test_proc_PW(self, mupdate, msleep, mpevents, msendcmd):
		avr = self.avr

		avr.proc_PW('STANDBY')
		self.assertEqual(avr.power, False)

		avr.proc_PW('ON')
		self.assertEqual(avr.power, True)

		self.assertRaises(RuntimeError, avr.proc_PW, 'foobar')

		avr.power = False
		msendcmd.assert_any_call('PW', 'STANDBY')

	def test_proc_MU(self):
		avr = self.avr

		avr.proc_MU('ON')
		self.assertEqual(avr._mute, True)

		avr.proc_MU('OFF')
		self.assertEqual(avr._mute, False)

		self.assertRaises(RuntimeError, avr.proc_MU, 'foobar')

	def test_proc_PS(self):
		avr = self.avr

		avr.proc_PS('FRONT A')
		self.assertEqual(avr._speakera, True)
		self.assertEqual(avr._speakerb, False)

		self.assertRaises(RuntimeError, avr.proc_PS, 'foobar')

	def test_proc_Z2(self):
		avr = self.avr

		avr.proc_Z2('MUOFF')
		self.assertEqual(avr._z2mute, False)

		self.assertRaises(RuntimeError, avr.proc_Z2, 'foobar')

	def test_proc_MS(self):
		avr = self.avr

		avr.proc_MS('STEREO')
		self.assertEqual(avr.ms, 'STEREO')

	def test_proc_ZM(self):
		avr = self.avr

		avr.proc_ZM('ON')
		self.assertEqual(avr._zm, True)

		avr.proc_ZM('OFF')
		self.assertEqual(avr._zm, False)

		self.assertRaises(RuntimeError, avr.proc_ZM, 'foobar')

	@mock.patch('denon.DenonAVR.process_events')
	def test_proc_MV(self, pe):
		avr = self.avr

		avr.proc_MV('MAX 80')
		self.assertEqual(avr._volmax, 81)

		avr.proc_MV('99')
		self.assertEqual(avr._vol, 0)

		avr.vol = 0

		# we don't call this as we don't get a response
		pe.assert_not_called()

		self.assertRaises(ValueError, setattr, avr, 'vol', 82)

	def test_readcmd(self):
		avr = self.avr

		# Test no pending cmd and that timeout is set
		timov = .5
		timovcur = [ timov ]
		def curtimo(*args):
			assert len(args) in (0, 1)

			if len(args):
				timovcur[0] = args[0]
			else:
				return timovcur[0]

		timo = mock.PropertyMock(side_effect=curtimo)
		type(avr._ser).timeout = timo
		avr._ser.read.side_effect = [ '' ]

		r = avr._readcmd(timo=0)

		# original value restored
		self.assertEqual(avr._ser.timeout, timov)

		# that the timeout was set
		timo.assert_any_call(0)

		# and it returned an empty command
		self.assertEqual(r, '')

		# that it got returned the the old value
		self.assertEqual(avr._ser.timeout, timov)

		avr._ser.read.side_effect = 'MUON\r'
		r = avr._readcmd(timo=1)

		self.assertEqual(r, 'MUON')
		self.assertEqual(avr._ser.timeout, timov)
