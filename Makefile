clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +

clean-build:
	rm -rf build/ dist/ *.egg-info

test: clean-pyc
	tox

clean-test: clean-pyc
	tox --recreate

build: clean-build test
	python setup.py sdist
