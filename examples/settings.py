"""setting module for your project"""
import os
import logging

import httpx

from ant_nest.exceptions import ExceptionFilter

# your ant`s class modules or packages
ANT_PACKAGES = ["ants"]
ANT_ENV = os.getenv("ANT_ENV", "development")


# httpx config, see httpx.Client.__init__ for more detail
HTTPX_CONFIG = {
    "timeout": 5.0,
    "max_redirects": 20,
    "pool_limits": httpx.PoolLimits(soft_limit=10, hard_limit=100),
    "trust_env": True,
    "proxies": None,
    "auth": None,
    "headers": None,
    "cookies": None,
}


POOL_CONFIG = {
    "limit": 1,
}
REPORTER = {
    "slot": 60,
}


# ANT config
HTTP_RETRIES = 3
HTTP_RETRY_DELAY = 1

# logger config
logging.basicConfig(level=logging.INFO)
logging.getLogger().addFilter(ExceptionFilter())
