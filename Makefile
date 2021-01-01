all: test

version = `python -c 'import pkg_resources; print(pkg_resources.get_distribution("ant_nest").version)'`

prepare_test_env:
	docker run --name test_httpbin --rm -d -p 8080:80 kennethreitz/httpbin@sha256:ebfa1bd104bc80c4da84da4a2a3abfb0dbd82d7bb536bb51000c1b330d8dc34f

destroy_test_env:
	docker stop test_httpbin

install:
	poetry install

test: install
	black ant_nest tests examples --check
	flake8 ant_nest tests examples
	mypy --ignore-missing-imports ant_nest
	pytest --cov ant_nest --cov-report term-missing

integration_test: install
	cd examples && ant_nest -a "*" && cd ../

tag: install
	git tag $(version) -m "Release of version $(version)"

pypi_release: install
	poetry publish

github_release:
	git push origin --tags

release: tag github_release pypi_release

clean:
	rm -rf .eggs *.egg-info dist build
