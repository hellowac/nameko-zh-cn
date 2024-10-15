from __future__ import absolute_import

from contextlib import contextmanager
from logging import getLogger

from nameko.containers import get_container_cls, get_service_name
from nameko.utils.concurrency import SpawningProxy


_log = getLogger(__name__)


class ServiceRunner(object):
    """允许用户并发提供多个服务。
    调用者可以为多个服务类注册名称，然后使用
    start 方法来提供它们，并使用 stop 和 kill 方法
    来停止它们。wait 方法将阻塞，直到所有服务停止。

    示例::

        runner = ServiceRunner(config)
        runner.add_service(Foobar)
        runner.add_service(Spam)

        add_sig_term_handler(runner.kill)

        runner.start()

        runner.wait()
    """

    def __init__(self, config):
        self.service_map = {}
        self.config = config

        self.container_cls = get_container_cls(config)

    @property
    def service_names(self):
        return self.service_map.keys()

    @property
    def containers(self):
        return self.service_map.values()

    def add_service(self, cls):
        """将服务类添加到运行器中。
        对于给定的服务名称，最多只能有一个服务类。
        服务类必须在调用 start() 之前注册。
        """
        service_name = get_service_name(cls)
        container = self.container_cls(cls, self.config)
        self.service_map[service_name] = container

    def start(self):
        """启动所有注册的服务。

        每个服务都会使用 __init__ 方法中提供的容器
        类创建一个新容器。

        所有容器将并发启动，该方法将在所有容器完成
        启动例程之前阻塞。
        """
        service_names = ", ".join(self.service_names)
        _log.info("启动服务: %s", service_names)

        SpawningProxy(self.containers).start()

        _log.debug("服务已启动: %s", service_names)

    def stop(self):
        """并发停止所有正在运行的容器。
        该方法在所有容器停止之前将阻塞。
        """
        service_names = ", ".join(self.service_names)
        _log.info("停止服务: %s", service_names)

        SpawningProxy(self.containers).stop()

        _log.debug("服务已停止: %s", service_names)

    def kill(self):
        """并发杀死所有正在运行的容器。
        该方法将在所有容器停止之前将阻塞。
        """
        service_names = ", ".join(self.service_names)
        _log.info("杀死服务: %s", service_names)

        SpawningProxy(self.containers).kill()

        _log.debug("服务已被杀死: %s ", service_names)

    def wait(self):
        """等待所有正在运行的容器停止。"""
        try:
            SpawningProxy(self.containers, abort_on_error=True).wait()
        except Exception:
            # 如果一个容器失败，停止它的同伴并重新引发异常
            self.stop()
            raise


@contextmanager
def run_services(config, *services, **kwargs):
    """为上下文块提供多个服务。
    调用者可以指定多个服务类，然后在退出上下文块时
    停止（默认）或杀死它们。

    示例::

        with run_services(config, Foobar, Spam) as runner:
            # 与服务交互并在退出块时停止它们

        # 服务已停止


    可以通过关键字参数指定额外的配置，以供 :class:``ServiceRunner`` 实例使用::

        with run_services(config, Foobar, Spam, kill_on_exit=True):
            # 与服务交互

        # 服务已被杀死

    :Parameters:
        config : dict
            用于实例化服务容器的配置
        services : 服务定义
            在上下文块中提供的服务
        kill_on_exit : bool (default=False)
            如果为 ``True``，在退出上下文块时对服务容器调用 ``kill()``。
            否则在退出块时将调用 ``stop()``。

    :Returns: 配置好的 :class:`ServiceRunner` 实例

    """
    kill_on_exit = kwargs.pop("kill_on_exit", False)

    runner = ServiceRunner(config)
    for service in services:
        runner.add_service(service)

    runner.start()

    yield runner

    if kill_on_exit:
        runner.kill()
    else:
        runner.stop()
