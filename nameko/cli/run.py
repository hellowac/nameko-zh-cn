from __future__ import print_function

import errno
import inspect
import logging
import logging.config
import os
import re
import signal
import sys

import six
import yaml
import eventlet
from eventlet import backdoor

from nameko.constants import AMQP_URI_CONFIG_KEY
from nameko.exceptions import CommandError
from nameko.extensions import ENTRYPOINT_EXTENSIONS_ATTR
from nameko.runners import ServiceRunner


logger = logging.getLogger(__name__)

MISSING_MODULE_TEMPLATE = "^No module named '?{}'?$"


def is_type(obj):
    return isinstance(obj, six.class_types)


def is_entrypoint(method):
    return hasattr(method, ENTRYPOINT_EXTENSIONS_ATTR)


def import_service(module_name):
    parts = module_name.split(":", 1)
    if len(parts) == 1:
        module_name, obj = module_name, None
    else:
        module_name, obj = parts[0], parts[1]

    try:
        __import__(module_name)
    except ImportError as exc:
        if module_name.endswith(".py") and os.path.exists(module_name):
            raise CommandError(
                "Failed to find service, did you mean '{}'?".format(
                    module_name[:-3].replace('/', '.')
                )
            )

        missing_module_re = MISSING_MODULE_TEMPLATE.format(module_name)
        # 有没有更好的方法来做到这一点？

        if re.match(missing_module_re, str(exc)):
            raise CommandError(exc)

        # 找到模块，但在其他地方导入时引发了导入错误，让它冒泡（导致打印完整的堆栈跟踪）。
        raise

    module = sys.modules[module_name]

    if obj is None:
        found_services = []
        # 查找具有入口点的顶级对象。
        for _, potential_service in inspect.getmembers(module, is_type):
            if inspect.getmembers(potential_service, is_entrypoint):
                found_services.append(potential_service)

        if not found_services:
            raise CommandError(
                "Failed to find anything that looks like a service in module "
                "{!r}".format(module_name)
            )

    else:
        try:
            service_cls = getattr(module, obj)
        except AttributeError:
            raise CommandError(
                "Failed to find service class {!r} in module {!r}".format(
                    obj, module_name)
            )

        if not isinstance(service_cls, type):
            raise CommandError("Service must be a class.")

        found_services = [service_cls]

    return found_services


def setup_backdoor(runner, port):
    def _bad_call():
        raise RuntimeError(
            'This would kill your service, not close the backdoor. To exit, '
            'use ctrl-c.')
    socket = eventlet.listen(('localhost', port))
    # work around https://github.com/celery/kombu/issues/838
    socket.settimeout(None)
    gt = eventlet.spawn(
        backdoor.backdoor_server,
        socket,
        locals={
            'runner': runner,
            'quit': _bad_call,
            'exit': _bad_call,
        })
    return socket, gt


def run(services, config, backdoor_port=None):
    service_runner = ServiceRunner(config)
    for service_cls in services:
        service_runner.add_service(service_cls)

    def shutdown(signum, frame):
        # 信号处理程序由主循环运行，无法使用 eventlet 原语，因此我们必须在绿色线程中调用 `stop`。
        eventlet.spawn_n(service_runner.stop)

    signal.signal(signal.SIGTERM, shutdown)

    if backdoor_port is not None:
        setup_backdoor(service_runner, backdoor_port)

    service_runner.start()

    # 如果信号处理程序在 eventlet 正在等待套接字时触发，
    # `__main__` 绿色线程会收到一个 OSError(4) "Interrupted system call"。
    # 这是 eventlet hub 机制的副作用。为了保护 nameko 不受该异常的影响，
    # 我们将 `runner.wait` 调用包装在此处生成的绿色线程中，以便捕获（并静默）该异常。
    runnlet = eventlet.spawn(service_runner.wait)

    while True:
        try:
            runnlet.wait()
        except OSError as exc:
            if exc.errno == errno.EINTR:
                # 这是由信号处理程序引起的 OSError(4)。  
                # 忽略它并返回继续等待 runner。
                continue
            raise
        except KeyboardInterrupt:
            print()  # 在终端中显示类似于 bash 的 ^C 形式，看起来更好。
            try:
                service_runner.stop()
            except KeyboardInterrupt:
                print()  # as above
                service_runner.kill()
        else:
            # runner.wait completed
            break  # pragma: no cover (coverage problem on py39)


def main(args):
    if '.' not in sys.path:
        sys.path.insert(0, '.')

    if args.config:
        with open(args.config) as fle:
            config = yaml.safe_load(fle)
    else:
        config = {
            AMQP_URI_CONFIG_KEY: args.broker
        }

    if "LOGGING" in config:
        logging.config.dictConfig(config['LOGGING'])
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')

    services = []
    for path in args.services:
        services.extend(
            import_service(path)
        )

    run(services, config, backdoor_port=args.backdoor_port)
