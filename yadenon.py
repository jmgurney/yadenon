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

from twisted.internet.defer import inlineCallbacks, Deferred, returnValue
from twisted.protocols import basic
from twisted.test import proto_helpers
from twisted.trial import unittest
import mock
import time
import twisted.internet.serialport

__all__ = [ 'DenonAVR' ]

class DenonAVR(object,basic.LineReceiver):
	delimiter = '\r'
	timeOut = 1

	def __init__(self, serdev):
		'''Specify the serial device connected to the Denon AVR.'''

		self._ser = twisted.internet.serialport.SerialPort(self, serdev, None, baudrate=9600)
		self._cmdswaiting = {}

		self._power = None
		self._vol = None
		self._volmax = None
		self._speakera = None
		self._speakerb = None
		self._z2mute = None
		self._zm = None
		self._ms = None

	def _magic(cmd, attrname, settrans, args, doc):
		def getter(self):
			return getattr(self, attrname)

		def setter(self, arg):
			arg = settrans(arg)
			if arg != getattr(self, attrname):
				self._sendcmd(cmd, args[arg])

		return property(getter, setter, doc=doc)

	@property
	def ms(self):
		'Surround mode'

		return self._ms

	power = _magic('PW', '_power', bool, { True: 'ON', False: 'STANDBY' }, 'Power status, True if on')
	mute = _magic('MU', '_mute', bool, { True: 'ON', False: 'OFF' }, 'Mute speakers, True speakers are muted (no sound)')
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
		cmd = '%s%s' % (cmd, args)

		#print 'sendcmd:', `cmd`

		self.sendLine(cmd)

	def lineReceived(self, event):
		'''Process a line from the AVR.'''

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
		state of the object matches the amp.'''

		d = self._waitfor('PW')

		self._sendcmd('PW', '?')

		d = yield d

		d = self._waitfor('MVMAX')

		self._sendcmd('MV', '?')

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

		d = avr.update()

		self.assertEqual(self.tr.value(), 'PW?\r')

		avr.dataReceived('PWSTANDBY\r')

		avr.dataReceived('MV51\rMVMAX 80\r')

		d = yield d

		self.assertEqual(self.tr.value(), 'PW?\rMV?\r')

		self.assertEqual(avr.power, False)
		self.assertIsNone(d)

		self.tr.clear()

		d = avr.update()

		self.assertEqual(self.tr.value(), 'PW?\r')

		avr.dataReceived('PWON\rZMON\rMUOFF\rZ2MUOFF\rMUOFF\rPSFRONT A\r')

		avr.dataReceived('MSDIRECT\rMSDIRECT\rMSDIRECT\rMV51\rMVMAX 80\r')

		d = yield d

		self.assertEqual(self.tr.value(), 'PW?\rMV?\r')

		self.assertEqual(avr.power, True)
		self.assertIsNone(d)

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

	@inlineCallbacks
	def test_vol(self):
		avr = self.avr

		d = avr.update()

		self.assertEqual(self.tr.value(), 'PW?\r')

		avr.dataReceived('PWON\rZMON\rMUOFF\rZ2MUOFF\rMUOFF\rPSFRONT A\r')
		avr.dataReceived('MSDIRECT\rMSDIRECT\rMSDIRECT\rMV51\rMVMAX 80\r')

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

	def test_proc_MV(self):
		avr = self.avr

		avr.proc_MV('MAX 80')
		self.assertEqual(avr.volmax, 81)

		avr.proc_MV('99')
		self.assertEqual(avr.vol, 0)

		avr.vol = 0

		self.assertRaises(ValueError, setattr, avr, 'vol', 82)
