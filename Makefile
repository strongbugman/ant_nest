all: test

version=`python -c 'import ant_nest; print(ant_nest.__version__)'`

sdist:
	./setup.py sdist

clean:
	rm -rf .egg *.egg-info dist build

test:
	python setup.py test --addopts='--cov=.'

tag:
	git tag $(version) -m "Release of version $(version)"

pypi_release:
	./setup.py sdist upload -r pypi
