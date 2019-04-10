all: test

version=`python -c 'import ant_nest; print(ant_nest.__version__)'`

prepare_test_env:
	docker run --name test_httpbin --rm -d -p 8080:80 kennethreitz/httpbin@sha256:ebfa1bd104bc80c4da84da4a2a3abfb0dbd82d7bb536bb51000c1b330d8dc34f
	docker run --name test_squid --rm -d -p 3128:3128 -v `pwd`/tests/squid.conf:/etc/squid/squid.conf -v `pwd`/tests/squid.htpasswd:/etc/squid/squid.htpasswd minimum2scp/squid

destroy_test_env:
	docker stop test_httpbin test_squid

test:
	black ant_nest tests examples setup.py --check
	flake8 ant_nest tests examples setup.py
	mypy --ignore-missing-imports ant_nest
	python setup.py test --addopts='--cov ant_nest --cov-report term-missing'
	python setup.py install && cd examples && ant_nest -a "*" && cd ../

tag:
	git tag $(version) -m "Release of version $(version)"

sdist:
	./setup.py sdist

pypi_release:
	./setup.py sdist upload -r pypi

github_release:
	git push origin --tags

release: tag github_release pypi_release

clean:
	rm -rf .eggs *.egg-info dist build
