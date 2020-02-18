"""setting module for your project"""
import os
import logging
import asyncio

import httpx

from ant_nest.exceptions import ExceptionFilter

# your ant`s class modules or packages
ANT_PACKAGES = ["ants"]
ANT_ENV = os.getenv("ANT_ENV", "development")


# httpx config, see httpx.Client.__init__ for more detail
HTTPX_CONFIG = {
    "timeout": httpx.config.DEFAULT_TIMEOUT_CONFIG,
    "max_redirects": httpx.config.DEFAULT_MAX_REDIRECTS,
    "pool_limits": httpx.config.DEFAULT_POOL_LIMITS,
    "trust_env": True,
    "http2": False,
    "proxies": None,
    "auth": None,
    "headers": None,
    "cookies": None,
}


# ANT config
JOB_LIMIT = 50
HTTP_RETRIES = 0
HTTP_RETRY_DELAY = 0.1


if ANT_ENV in ("development", "testing"):
    logging.basicConfig(level=logging.DEBUG)
    asyncio.get_event_loop().set_debug(True)
else:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger().addFilter(ExceptionFilter())


# custom setting, eg:
# MYSQL_HOST = '127.0.0.1'
