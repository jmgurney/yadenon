test:
	echo yadenon.py | entr sh -c 'python -m coverage run -m unittest yadenon && coverage report --omit=t/\* -m'
