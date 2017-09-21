#!/usr/bin/env python

__author__ = 'John-Mark Gurney'
__copyright__ = 'Copyright 2017 John-Mark Gurney.  All rights reserved.'
__license__ = '2-clause BSD license'

# Copyright 2017, John-Mark Gurney
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies,
# either expressed or implied, of the Project.

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred, returnValue
from twisted.protocols import basic
from twisted.test import proto_helpers
from twisted.trial import unittest
import mock
import time
import twisted.internet.serialport

__all__ = [ 'DenonAVR' ]

class DenonAVR(object,basic.LineReceiver):
	'''A Twisted Protocol Handler for Denon Receivers.  This is not yet
	complete, but has basic functionally, and more will be added as
	needed.'''

	delimiter = '\r'	# line delimiter is the CR
	timeOut = 1

	def __init__(self, serdev):
		'''Specify the serial device connected to the Denon AVR.'''

		# XXX - is this needed?
		self._ser = twisted.internet.serialport.SerialPort(self, serdev, reactor, baudrate=9600)
		self._cmdswaiting = {}

		self._power = None
		self._vol = None
		self._mute = None
		self._volmax = None
		self._speakera = None
		self._speakerb = None
		self._source = None
		self._z2mute = None
		self._input = None
		self._zm = None
		self._ms = None

		self._eventsfuns = []

	def register(self, fun):
		'''Register a callback for when an attribute gets
		modified or changed.

		As this is async, this is useful to get notifications of
		when you change an attribute and the value of the amp does
		change.'''

		self._eventsfuns.append(fun)

	def unregister(self, fun):
		'''Unregister a function that was previously registered with
		register.'''

		self._eventsfuns.remove(fun)

	def _notify(self, attr):
		for i in self._eventsfuns:
			# XXX - supress exceptions?
			i(attr)

	def _magic(cmd, attrname, settrans, args, doc):
		def getter(self):
			return getattr(self, attrname)

		def setter(self, arg):
			arg = settrans(arg)
			if arg != getattr(self, attrname):
				try:
					self._sendcmd(cmd, args[arg])
				except KeyError:
					raise ValueError(arg)

		return property(getter, setter, doc=doc)

	@property
	def ms(self):
		'Surround mode'

		return self._ms

	power = _magic('PW', '_power', bool, { True: 'ON', False: 'STANDBY' }, 'Power status, True if on')
	input = _magic('SI', '_input', str, { x:x for x in ('PHONO', 'TUNER', 'CD', 'V.AUX', 'DVD', 'TV', 'SAT/CBL', 'DVR', ) }, 'Audio Input Source')
	source = _magic('SD', '_source', str, { x:x for x in ('AUTO', 'HDMI', 'DIGITAL', 'ANALOG', ) }, 'Source type, can be one of AUTO, HDMI, DIGITAL, or ANALOG')
	mute = _magic('MU', '_mute', bool, { True: 'ON', False: 'OFF' }, 'Mute speakers, True speakers are muted (no sound)')
	zm = _magic('ZM', '_zm', bool, { True: 'ON', False: 'OFF' }, 'Main Zone On, True if on')
	z2mute = _magic('Z2MU', '_z2mute', bool, { True: 'ON', False: 'OFF' }, 'Mute Zone 2 speakers, True speakers are muted (no sound)')

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

		self._sendcmd('MV', arg)

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

		self._notify('power')

	def proc_MU(self, arg):
		if arg == 'ON':
			self._mute = True
		elif arg == 'OFF':
			self._mute = False
		else:
			raise RuntimeError('unknown MU arg: %s' % `arg`)

		self._notify('mute')

	def proc_ZM(self, arg):
		if arg == 'ON':
			self._zm = True
		elif arg == 'OFF':
			self._zm = False
		else:
			raise RuntimeError('unknown ZM arg: %s' % `arg`)

		self._notify('zm')

	def proc_MV(self, arg):
		if arg[:4] ==  'MAX ':
			self._volmax = self._parsevolarg(arg[4:])
			self._notify('volmax')
		else:
			self._vol = self._parsevolarg(arg)
			self._notify('vol')

	def proc_MS(self, arg):
		self._ms = arg

	def proc_SI(self, arg):
		self._input = arg
		self._notify('input')

	def proc_SD(self, arg):
		self._source = arg
		self._notify('source')

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
		cmd = '%s%s' % (cmd, args)

		#print 'sendcmd:', `cmd`

		self.sendLine(cmd)

	def lineReceived(self, event):
		'''Process a line from the AVR.  This is internal and will
		be called by LineReceiver.'''

		#print 'lR:', `event`
		if len(event) >= 2:
			fun = getattr(self, 'proc_%s' % event[:2])
			fun(event[2:])

			for d in self._cmdswaiting.pop(event[:2], []):
				d.callback(event)

	def _waitfor(self, resp):
		d = Deferred()

		cmd = resp[:2]
		self._cmdswaiting.setdefault(cmd, []).append(d)

		if len(resp) > 2:
			@inlineCallbacks
			def extraresp(d=d):
				while True:
					r = yield d
					if r.startswith(resp):
						returnValue(r)

					d = self._waitfor(cmd)

			d = extraresp()

		return d

	@inlineCallbacks
	def update(self):
		'''Update the status of the AVR.  This ensures that the
		state of the object matches the amp.  Returns a Deferred.
		When the deferred fires, then all the internal state has
		been updated and can be examined.'''

		d = self._waitfor('PW')

		self._sendcmd('PW', '?')

		d = yield d

		d = self._waitfor('MVMAX')

		self._sendcmd('MV', '?')

		d = yield d

		d = self._waitfor('SI')

		self._sendcmd('SI', '?')

		d = yield d

class TestDenon(unittest.TestCase):
	TEST_DEV = '/dev/tty.usbserial-FTC8DHBJ'

	def test_comms(self): # pragma: no cover
		# comment out to make it easy to restore skip
		self.skipTest('perf')

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
	@mock.patch('twisted.internet.serialport.SerialPort')
	def setUp(self, sfu):
		self.avr = DenonAVR('null')
		self.tr = proto_helpers.StringTransport()
		self.avr.makeConnection(self.tr)

	@staticmethod
	def getTimeout():
		return .3

	@inlineCallbacks
	def test_update(self):
		avr = self.avr

		dfr = avr.update()

		# get the first stage
		self.assertEqual(self.tr.value(), 'PW?\r')

		avr.dataReceived('PWSTANDBY\r')
		avr.dataReceived('MV51\rMVMAX 80\r')
		avr.dataReceived('SIPHONO\r')

		d = yield dfr

		# get the second stage
		self.assertEqual(self.tr.value(), 'PW?\rMV?\rSI?\r')

		self.assertEqual(avr.power, False)
		self.assertIsNone(d)

		d = yield dfr

		self.assertEqual(self.tr.value(), 'PW?\rMV?\rSI?\r')

		self.assertEqual(avr.input, 'PHONO')
		self.assertIsNone(d)

		self.tr.clear()

		d = avr.update()

		self.assertEqual(self.tr.value(), 'PW?\r')

		avr.dataReceived('PWON\rZMON\rMUOFF\rZ2MUOFF\rMUOFF\rPSFRONT A\r')
		avr.dataReceived('MSDIRECT\rMSDIRECT\rMSDIRECT\rMV51\rMVMAX 80\r')
		avr.dataReceived('SIDVD\r')

		d = yield d

		self.assertEqual(self.tr.value(), 'PW?\rMV?\rSI?\r')

		self.assertEqual(avr.power, True)
		self.assertIsNone(d)
		self.assertEqual(avr.input, 'DVD')

	def test_realsequences(self):
		avr = self.avr

		avr.dataReceived('PSFRONT A\rSITUNER\rMSSTEREO\rSDANALOG\r')

	@inlineCallbacks
	def test_waitfor(self):
		avr = self.avr

		avr.proc_AB = lambda arg: None

		d = avr._waitfor('AB123')

		# make sure that matching, but different response doesn't trigger
		avr.dataReceived('ABABC\r')
		self.assertFalse(d.called)

		# make sure that it triggers
		avr.dataReceived('AB123\r')

		self.assertTrue(d.called)

		d = yield d

		# and we get correct response
		self.assertEqual(d, 'AB123')

	def test_register(self):
		avr = self.avr

		efun = mock.MagicMock()
		avr.register(efun)

		avr.proc_MV('41')

		efun.assert_called_once_with('vol')
		efun.reset_mock()

		avr.proc_MV('MAX 80')

		efun.assert_called_once_with('volmax')
		efun.reset_mock()

		avr.proc_PW('ON')

		efun.assert_called_once_with('power')
		efun.reset_mock()

		avr.proc_MU('ON')

		efun.assert_called_once_with('mute')
		efun.reset_mock()

		avr.proc_ZM('ON')

		efun.assert_called_once_with('zm')
		efun.reset_mock()

		avr.proc_SI('TUNER')

		efun.assert_called_once_with('input')
		efun.reset_mock()

		avr.proc_SD('ANALOG')

		efun.assert_called_once_with('source')
		efun.reset_mock()

		avr.unregister(efun)
		avr.proc_PW('ON')

		self.assertEqual(efun.call_count, 0)

	@inlineCallbacks
	def test_vol(self):
		avr = self.avr

		d = avr.update()

		self.assertEqual(self.tr.value(), 'PW?\r')

		avr.dataReceived('PWON\rZMON\rMUOFF\rZ2MUOFF\rMUOFF\rPSFRONT A\r')
		avr.dataReceived('MSDIRECT\rMSDIRECT\rMSDIRECT\rMV51\rMVMAX 80\r')
		avr.dataReceived('SIPHOTO\r')

		d = yield d

		self.tr.clear()

		avr.vol = 20

		self.assertEqual(self.tr.value(), 'MV19\r')

	def test_proc_events(self):
		avr = self.avr

		avr.dataReceived('PWON\r')

		self.assertEqual(avr.power, True)

		avr.dataReceived('MUON\r' + 'PWON\r')

		self.assertEqual(avr.mute, True)
		self.assertEqual(avr.power, True)

		avr.dataReceived('PWSTANDBY\r')

		self.assertEqual(avr.power, False)

	@mock.patch('yadenon.DenonAVR.sendLine')
	def test_proc_PW(self, sendline):
		avr = self.avr

		avr.proc_PW('STANDBY')
		self.assertEqual(avr.power, False)

		avr.proc_PW('ON')
		self.assertEqual(avr.power, True)

		self.assertRaises(RuntimeError, avr.proc_PW, 'foobar')

		avr.power = False
		sendline.assert_any_call('PWSTANDBY')

	def test_proc_MU(self):
		avr = self.avr

		avr.proc_MU('ON')
		self.assertEqual(avr.mute, True)

		avr.proc_MU('OFF')
		self.assertEqual(avr.mute, False)

		self.assertRaises(RuntimeError, avr.proc_MU, 'foobar')

	@mock.patch('yadenon.DenonAVR.sendLine')
	def test_mute(self, sendline):
		avr = self.avr

		avr.mute = True
		sendline.assert_any_call('MUON')

		# Verify the transition doesn't happen
		self.assertFalse(avr.mute)

		# till we get notification
		avr.proc_MU('ON')
		self.assertTrue(avr.mute)

		avr.mute = False
		sendline.assert_any_call('MUOFF')

	def test_proc_PS(self):
		avr = self.avr

		avr.proc_PS('FRONT A')
		self.assertEqual(avr._speakera, True)
		self.assertEqual(avr._speakerb, False)

		self.assertRaises(RuntimeError, avr.proc_PS, 'foobar')

	def test_proc_Z2(self):
		avr = self.avr

		avr.proc_Z2('MUOFF')
		self.assertEqual(avr.z2mute, False)

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

	@mock.patch('yadenon.DenonAVR.sendLine')
	def test_zm(self, sendline):
		avr = self.avr

		avr.zm = True
		sendline.assert_any_call('ZMON')

		# Verify the transition doesn't happen
		self.assertFalse(avr.zm)

		# till we get notification
		avr.proc_ZM('ON')
		self.assertTrue(avr.zm)

		avr.zm = False
		sendline.assert_any_call('ZMOFF')

	def test_proc_MV(self):
		avr = self.avr

		avr.proc_MV('MAX 80')
		self.assertEqual(avr.volmax, 81)

		avr.proc_MV('99')
		self.assertEqual(avr.vol, 0)

		avr.vol = 0

		self.assertRaises(ValueError, setattr, avr, 'vol', 82)

	def test_proc_SI(self):
		avr = self.avr
		avr.proc_SI('PHONO')
		self.assertEqual(avr.input, 'PHONO')

		avr.proc_SI('TUNER')
		self.assertEqual(avr.input, 'TUNER')

	@mock.patch('yadenon.DenonAVR.sendLine')
	def test_input(self, sendline):
		avr = self.avr

		avr.input = 'PHONO'
		sendline.assert_any_call('SIPHONO')

		# Verify the transition doesn't happen
		self.assertIsNone(avr.input)

		# till we get notification
		avr.proc_SI('PHONO')
		self.assertEqual(avr.input, 'PHONO')

		avr.input = 'TUNER'
		sendline.assert_any_call('SITUNER')

		avr.input = 'CD'
		avr.input = 'V.AUX'
		avr.input = 'DVD'
		avr.input = 'TV'
		avr.input = 'SAT/CBL'
		avr.input = 'DVR'

		self.assertRaises(ValueError, setattr, avr, 'input', 'bogus')
		self.assertRaises(ValueError, setattr, avr, 'input', True)
		self.assertRaises(ValueError, setattr, avr, 'input', 34)

	@mock.patch('yadenon.DenonAVR.sendLine')
	def test_source(self, sendline):
		avr = self.avr

		avr.source = 'AUTO'
		sendline.assert_any_call('SDAUTO')

		# Verify the transition doesn't happen
		self.assertIsNone(avr.source)

		# till we get notification
		avr.proc_SD('AUTO')
		self.assertEqual(avr.source, 'AUTO')

		avr.source = 'HDMI'
		sendline.assert_any_call('SDHDMI')

		avr.source = 'DIGITAL'
		avr.source = 'ANALOG'

		self.assertRaises(ValueError, setattr, avr, 'source', 'bogus')
		self.assertRaises(ValueError, setattr, avr, 'source', True)
		self.assertRaises(ValueError, setattr, avr, 'source', 34)
