"""CLI entry points"""
import typing
import argparse
import inspect
import os
import sys
import shutil
import asyncio
from importlib import import_module
from pkgutil import iter_modules
import signal
import functools
from asyncio.queues import QueueEmpty

from .ant import Ant
from . import __version__

__signal_count = 0


def get_ants(paths: typing.List[str]) -> typing.Dict[str, typing.Type[Ant]]:
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
            if isinstance(obj, type) and issubclass(
                    obj, Ant) and obj is not Ant:
                results[module.__name__ + '.' + obj.__name__] = obj
    return results


def shutdown_ant(ants: typing.List[Ant]):
    global __signal_count
    ant_names = '+'.join([ant.name for ant in ants])

    if __signal_count == 1:
        print('Receive shutdown command twice, ant {:s} shutdown '
              'immediately'.format(ant_names))
        sys.exit()
    __signal_count += 1

    print('Graceful shutdown {:s}...Try again to force '
          'shutdown'.format(ant_names))

    # drop waiting coroutines
    for ant in ants:
        ant._is_closed = True
        while True:
            try:
                ant._queue.get_nowait()
            except QueueEmpty:
                break


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--ants',
                        help='ant names, multi name split by space')
    parser.add_argument('-l', '--list', help='list ants', action='store_true')
    parser.add_argument('-v', '--version', help='get package version',
                        action='store_true')
    parser.add_argument('-c', '--project', help='project name')
    args = parser.parse_args(args)
    sys.path.append(os.getcwd())

    if args.version:
        print(__version__)
        exit()
    elif args.project:
        from . import _settings_example
        try:
            os.mkdir(args.project)
        except FileExistsError:
            pass
        os.mkdir(os.path.join(args.project, 'ants'))
        shutil.copyfile(_settings_example.__file__,
                        os.path.join(args.project, 'settings.py'))
        exit()
    # in one project
    try:
        import settings
    except ImportError as e:
        print(e)
        print('Are "settings.py" created?')
        exit(-1)
    try:
        ants = get_ants(settings.ANT_PACKAGES)
    except Exception as e:
        print('There is a problem with finding and loading ants:')
        raise e

    if args.list:
        if len(ants) == 0:
            print('Can`t find any ant from ' + ','.join(settings.ANT_PACKAGES))
            exit(-1)
        else:
            print('\n'.join(ants.keys()))
    elif args.ants is not None:
        selected_ants: typing.List[Ant] = []
        for name in args.ants.split('+'):
            if name in ants:
                selected_ants.append(ants[name]())
            else:
                print('Can not find ant by the name "{:s}"'.format(name))
                exit(-1)

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT,
                                functools.partial(shutdown_ant, selected_ants))
        loop.add_signal_handler(signal.SIGTERM,
                                functools.partial(shutdown_ant, selected_ants))
        loop.run_until_complete(
            asyncio.gather(*(ant.main() for ant in selected_ants)))


if __name__ == '__main__':  # pragma: no cover
    main()
