all: test

version=`python -c 'import ant_nest; print(ant_nest.__version__)'`

prepare_test_env:
	docker run --name test_redis --rm -d -p 6379:6379 redis
	docker run --name test_mariadb --rm -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=letmein mariadb
	docker run --name test_httpbin --rm -d -p 8080:8080 kennethreitz/httpbin
	docker run --name test_squid --rm -d -p 3128:3128 -v `pwd`/tests/squid.conf:/etc/squid/squid.conf -v `pwd`/tests/squid.htpasswd:/etc/squid/squid.htpasswd minimum2scp/squid

destroy_test_env:
	docker stop test_redis test_mariadb test_httpbin test_squid

test:
	python setup.py test --addopts='--cov=.'

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
	rm -rf .egg *.egg-info dist build
