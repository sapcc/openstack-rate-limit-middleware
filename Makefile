clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +

clean-build:
	rm -rf build/ dist/ *.egg-info

test: clean-pyc
	tox

test-local:
	docker run -d --name redis -p 6379:6379 redis:latest && make test; docker rm -f redis

clean-test: clean-pyc
	tox --recreate

build: clean-build test
	python setup.py sdist

docs: 
	tox -e docs

