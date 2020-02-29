import sys
import os
from unittest import mock

import pytest

from ant_nest.ant import CliAnt
from ant_nest.cli import get_ants
from ant_nest import cli


def test_cli_get_ants():
    ants = get_ants(["ant_nest", "tests"])
    assert CliAnt is list(ants.values())[0]


def test_cli_shutdown():
    ant = CliAnt()
    cli.shutdown_ant([ant])
    assert ant.pool.closed

    with pytest.raises(SystemExit):
        cli.shutdown_ant([ant])


def test_cli():
    httpbin_base_url = os.getenv("TEST_HTTPBIN", "http://localhost:8080/")

    with pytest.raises(SystemExit):
        cli.main(["-v"])

    with pytest.raises(SystemExit):  # no settings.py
        cli.main(["-l"])

    with pytest.raises(SystemExit), mock.patch("IPython.embed"):  # no settings.py
        cli.main(["-u", httpbin_base_url])

    from ant_nest import _settings_example as settings

    # mock settings.py import
    sys.modules["settings"] = settings

    settings.ANT_PACKAGES = ["NoAnts"]
    with pytest.raises(ModuleNotFoundError):  # can`t import NoAnts
        cli.main(["-l"])

    settings.ANT_PACKAGES = ["ant_nest.items"]
    with pytest.raises(SystemExit):  # no ants can be found
        cli.main(["-l"])

    settings.ANT_PACKAGES = ["tests"]
    cli.main(["-l"])

    with pytest.raises(SystemExit):  # FakeAnt not exist
        cli.main(["-a" "FakeAnt"])
        cli.main(["-l"])

    with pytest.raises(SystemExit), mock.patch("os.mkdir", lambda x: None), mock.patch(
        "shutil.copyfile", lambda *args: None
    ):
        cli.main(["-c" "."])

    cli.main(["-a" "tests.test_cli.CliAnt"])
