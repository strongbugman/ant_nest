"""CLI entry points"""
from typing import Type, Dict, List
import argparse
import inspect
import os
import sys
import asyncio
from importlib import import_module
from pkgutil import iter_modules
from traceback import format_exc

from .ant import Ant


def get_ants(paths: List[str]) -> Dict[str, Type[Ant]]:
    """Get ant classes by package path"""
    modules = []
    results = {}
    # get all modules from packages and subpackages
    for path in paths:
        module = import_module(path)
        modules.append(module)
        if hasattr(module, '__path__'):
            package_path = []
            for _, name, ispkg in iter_modules(module.__path__):
                next_path = path + '.' + name
                if ispkg:
                    package_path.append(next_path)
                else:
                    modules.append(import_module(next_path))
            if len(package_path) > 0:
                results.update(get_ants(package_path))
    # get and sift ant class obj from modules
    for module in modules:
        for name, obj in inspect.getmembers(module):
            if isinstance(obj, type) and issubclass(obj, Ant) and obj is not Ant:
                results[module.__name__ + '.' + obj.__name__] = obj
    return results


async def run_ant(ant_cls: Type[Ant]):
    ant = ant_cls()
    await ant.main()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--ant', help='ant name')
    parser.add_argument('-l', '--list', help='list ants', action='store_true')
    args = parser.parse_args()
    sys.path.append(os.getcwd())
    try:
        import settings
    except ImportError:
        print('Please create "settings.py" in project root directory or use the command in project root directory')
        exit(-1)
    try:
        ants = get_ants(settings.ANT_PACKAGES)
    except Exception as e:
        print('There is problem when finding and loading ants:')
        print(format_exc())
        exit(-1)
    if args.list:
        if len(ants) == 0:
            print('Can`t find any ant from ' + ','.join(settings.ANT_PACKAGES))
            exit(-1)
        else:
            print('\n'.join(ants.keys()))
    elif args.ant is not None:
        ant_name = args.ant
        if ant_name in ants:
            asyncio.get_event_loop().run_until_complete(run_ant(ants[ant_name]))
        else:
            print('Can not find ant by the name "{:s}"'.format(ant_name))
            exit(-1)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
