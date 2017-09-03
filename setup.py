try:
	from setuptools import setup
except ImportError:
	from distutils.core import setup

setup(name='yadenon',
      version='2.0.0',
      description='Yet Anoter Python Denon AVR module',
      author='John-Mark Gurney',
      author_email='jmg@funkthat.com',
      url='https://github.com/jmgurney/yadenon',
      py_modules=['yadenon'],
      install_requires=[
          'mock',
          'twisted',
          'pyserial',
          ],
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: BSD License',
          'Operating System :: MacOS :: MacOS X',
          'Operating System :: Microsoft :: Windows',
          'Operating System :: POSIX',
          'Programming Language :: Python',
          'Topic :: Software Development :: Libraries :: Python Modules',
          ],
     )
