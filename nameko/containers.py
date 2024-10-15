from __future__ import absolute_import, unicode_literals

import inspect
import sys
import uuid
from collections import deque
from logging import getLogger

import eventlet
import six
from eventlet.event import Event
from eventlet.greenpool import GreenPool
from greenlet import GreenletExit  # pylint: disable=E0611

from nameko import serialization
from nameko.constants import (
    CALL_ID_STACK_CONTEXT_KEY,
    DEFAULT_MAX_WORKERS,
    DEFAULT_PARENT_CALLS_TRACKED,
    MAX_WORKERS_CONFIG_KEY,
    PARENT_CALLS_CONFIG_KEY,
)
from nameko.exceptions import ConfigurationError, ContainerBeingKilled
from nameko.extensions import ENTRYPOINT_EXTENSIONS_ATTR, is_dependency, iter_extensions
from nameko.log_helpers import make_timing_logger
from nameko.utils import import_from_path
from nameko.utils.concurrency import SpawningSet


_log = getLogger(__name__)
_log_time = make_timing_logger(_log)

if six.PY2:  # pragma: no cover
    is_method = inspect.ismethod
else:  # pragma: no cover
    is_method = inspect.isfunction


def get_service_name(service_cls):
    """获取微服务名称"""

    service_name = getattr(service_cls, "name", None)
    if service_name is None:
        raise ConfigurationError(
            "Service class 必须定义 `name` 属性 ({}.{})".format(
                service_cls.__module__, service_cls.__name__
            )
        )
    if not isinstance(service_name, six.string_types):
        raise ConfigurationError(
            "Service name 属性必须是string类型 ({}.{}.name)".format(
                service_cls.__module__, service_cls.__name__
            )
        )
    return service_name


def get_container_cls(config):
    """获取容器类"""

    class_path = config.get("SERVICE_CONTAINER_CLS")
    return import_from_path(class_path) or ServiceContainer


def new_call_id():
    return str(uuid.uuid4())


class WorkerContext(object):
    """工作者上下文"""

    _call_id = None
    _call_id_stack = None
    _parent_call_id_stack = None

    def __init__(
        self, container, service, entrypoint, args=None, kwargs=None, data=None
    ):
        self.container = container
        self.config = self.container.config

        self.service = service
        self.entrypoint = entrypoint
        self.service_name = self.container.service_name

        self.args = args if args is not None else ()
        self.kwargs = kwargs if kwargs is not None else {}
        self.data = data if data is not None else {}

        self._parent_call_id_stack = self.data.pop(CALL_ID_STACK_CONTEXT_KEY, [])

    @property
    def call_id_stack(self):
        if self._call_id_stack is None:
            parent_calls_tracked = self.container.config.get(
                PARENT_CALLS_CONFIG_KEY, DEFAULT_PARENT_CALLS_TRACKED
            )
            stack_length = parent_calls_tracked + 1

            self._call_id_stack = deque(maxlen=stack_length)
            self._call_id_stack.extend(self._parent_call_id_stack)
            self._call_id_stack.append(self.call_id)
        return list(self._call_id_stack)

    @property
    def call_id(self):
        if self._call_id is None:
            self._call_id = "{}.{}.{}".format(
                self.service_name, self.entrypoint.method_name, new_call_id()
            )
        return self._call_id

    @property
    def context_data(self):
        data = self.data.copy()
        data[CALL_ID_STACK_CONTEXT_KEY] = self.call_id_stack
        return data

    @property
    def origin_call_id(self):
        if self._parent_call_id_stack:
            return self._parent_call_id_stack[0]

    @property
    def immediate_parent_call_id(self):
        if self._parent_call_id_stack:
            return self._parent_call_id_stack[-1]

    def __repr__(self):
        cls_name = type(self).__name__
        service_name = self.service_name
        method_name = self.entrypoint.method_name
        return "<{} [{}.{}] at 0x{:x}>".format(
            cls_name, service_name, method_name, id(self)
        )


class ServiceContainer(object):
    """服务容器"""

    def __init__(self, service_cls, config):
        self.service_cls = service_cls
        self.config = config

        self.service_name = get_service_name(service_cls)
        self.shared_extensions = {}

        self.max_workers = config.get(MAX_WORKERS_CONFIG_KEY) or DEFAULT_MAX_WORKERS

        self.serializer, self.accept = serialization.setup(self.config)

        self.entrypoints = SpawningSet()
        self.dependencies = SpawningSet()
        self.subextensions = SpawningSet()

        for attr_name, dependency in inspect.getmembers(service_cls, is_dependency):
            bound = dependency.bind(self.interface, attr_name)
            self.dependencies.add(bound)
            self.subextensions.update(iter_extensions(bound))

        for method_name, method in inspect.getmembers(service_cls, is_method):
            entrypoints = getattr(method, ENTRYPOINT_EXTENSIONS_ATTR, [])
            for entrypoint in entrypoints:
                bound = entrypoint.bind(self.interface, method_name)
                self.entrypoints.add(bound)
                self.subextensions.update(iter_extensions(bound))

        self.started = False
        self._worker_pool = GreenPool(size=self.max_workers)

        self._worker_threads = {}
        self._managed_threads = {}
        self._being_killed = False
        self._died = Event()

    @property
    def extensions(self):
        return SpawningSet(self.entrypoints | self.dependencies | self.subextensions)

    @property
    def interface(self):
        """一个供扩展使用的此容器的接口。"""
        return self

    def start(self):
        """通过启动该容器的所有扩展来启动容器。"""
        _log.debug("starting %s", self)
        self.started = True

        with _log_time("started %s", self):
            self.extensions.all.setup()
            self.extensions.all.start()

    def stop(self):
        """优雅地停止容器。

        首先，所有入口点都会被要求执行 `stop()`。这确保不会启动新的工作线程。

        当对扩展调用 `stop()` 时，扩展有责任优雅地关闭，并且只有在它们停止后才返回。

        在所有入口点停止后，容器会等待所有活跃的工作线程完成。

        在所有活跃的工作线程停止后，容器会停止所有依赖提供者。

        此时，应该不再有托管线程。如果仍然有托管线程，它们将被容器终止。
        """
        if self._died.ready():
            _log.debug("already stopped %s", self)
            return

        if self._being_killed:
            # 当一个容器由一个运行器托管并在其 kill 方法中让出控制时，这种竞争条件可能会发生；
            # 如果调度不幸，运行器将尝试在 `self._died` 结果之前调用 `stop()`。
            _log.debug("already being killed %s", self)
            try:
                self._died.wait()
            except Exception:
                pass  # don't re-raise if we died with an exception
            return

        _log.debug("stopping %s", self)

        with _log_time("stopped %s", self):
            # 入口点必须在依赖项之前停止，以确保正在运行的工作线程能够成功完成。
            self.entrypoints.all.stop()

            # 可能仍然有一些正在运行的工作线程，我们必须等待它们完成后才能停止依赖项。
            self._worker_pool.waitall()

            # 现在可以安全地停止任何依赖项，因为没有活动的工作线程可能正在使用它。
            self.dependencies.all.stop()

            # 最后，停止剩余的扩展。
            self.subextensions.all.stop()

            # 以及它们生成的任何托管线程。
            self._kill_managed_threads()

            self.started = False

            # if `kill` is called after `stop`, they race to send this
            # 如果在 `stop` 之后调用 `kill` ，它们会竞争发送这个。
            if not self._died.ready():
                self._died.send(None)

    def kill(self, exc_info=None):
        """以半优雅的方式终止容器。

        首先终止入口点，然后是任何活跃的工作线程。接下来，终止依赖项。最后，终止任何剩余的托管线程。

        如果提供了 ``exc_info``，异常将由 :meth:`~wait` 引发。
        """
        if self._being_killed:
            # 如果托管线程在容器被终止时以异常退出，或者多个错误同时发生，就会发生这种情况
            _log.debug("已经在终止 %s ... 等待死亡", self)
            try:
                self._died.wait()
            except:
                pass  # 如果我们以异常死亡，则不重新引发
            return

        self._being_killed = True

        if self._died.ready():
            _log.debug("已经停止 %s", self)
            return

        if exc_info is not None:
            _log.info("因 %s 而终止 %s", self, exc_info[1])
        else:
            _log.info("终止 %s", self)

        # 防止在终止过程中抛出异常的扩展；容器已经因异常而死亡，因此忽略其他任何异常
        def safely_kill_extensions(ext_set):
            try:
                ext_set.kill()
            except Exception as exc:
                _log.warning("扩展在终止期间引发了 `%s`", exc)

        safely_kill_extensions(self.entrypoints.all)
        self._kill_worker_threads()
        safely_kill_extensions(self.extensions.all)
        self._kill_managed_threads()

        self.started = False

        # 如果在 `stop` 之后调用 `kill`，它们会竞争发送这个
        if not self._died.ready():
            self._died.send(None, exc_info)

    def wait(self):
        """阻塞直到容器已停止。

        如果容器因异常而停止，``wait()`` 将引发该异常。

        在托管线程或工作生命周期（例如在 :meth:`DependencyProvider.worker_setup` 内部）
        中引发的任何未处理异常将导致容器被 ``kill()``，并且在 ``wait()`` 中引发该异常。
        """
        return self._died.wait()

    def spawn_worker(
        self, entrypoint, args, kwargs, context_data=None, handle_result=None
    ):
        """为运行由 `entrypoint` 装饰的服务方法生成一个工作线程。

        ``args`` 和 ``kwargs`` 用作服务方法的参数。

        ``context_data`` 用于初始化 ``WorkerContext``。

        ``handle_result`` 是一个可选函数，可能由入口点传入。
        它在服务方法返回的结果或引发的错误时被调用。
        如果提供，则必须返回一个值用于 ``result`` 和 ``exc_info``，以便传播到依赖项；
        这些值可能与服务方法返回的值不同。
        """

        if self._being_killed:
            _log.info("由于正在被终止，阻止工作线程的生成")
            raise ContainerBeingKilled()

        service = self.service_cls()
        worker_ctx = WorkerContext(
            self, service, entrypoint, args, kwargs, data=context_data
        )

        _log.debug("生成 %s", worker_ctx)
        gt = self._worker_pool.spawn(self._run_worker, worker_ctx, handle_result)
        gt.link(self._handle_worker_thread_exited, worker_ctx)

        self._worker_threads[worker_ctx] = gt
        return worker_ctx

    def spawn_managed_thread(self, fn, identifier=None):
        """生成一个托管线程以代表扩展运行 ``fn``。
        传入的 `identifier` 将包含在与该线程相关的日志中，默认情况下如果已设置则为 `fn.__name__`。

        在 ``fn`` 内部引发的任何未捕获错误将导致容器被终止。

        终止生成的线程的责任在于调用者。
        如果在 :meth:`ServiceContainer.stop` 期间所有扩展停止后它们仍在运行，线程将自动被终止。

        扩展应该将所有线程生成委托给容器。
        """
        if identifier is None:
            identifier = getattr(fn, "__name__", "<unknown>")

        gt = eventlet.spawn(fn)
        self._managed_threads[gt] = identifier
        gt.link(self._handle_managed_thread_exited, identifier)
        return gt

    def _run_worker(self, worker_ctx, handle_result):
        _log.debug("正在设置 %s", worker_ctx)

        _log.debug(
            "对于 %s 的调用栈: %s", worker_ctx, "->".join(worker_ctx.call_id_stack)
        )

        with _log_time("运行工作线程 %s", worker_ctx):
            self._inject_dependencies(worker_ctx)
            self._worker_setup(worker_ctx)

            result = exc_info = None
            method_name = worker_ctx.entrypoint.method_name
            method = getattr(worker_ctx.service, method_name)
            try:
                _log.debug("正在调用处理器 %s", worker_ctx)

                with _log_time("运行处理器 %s", worker_ctx):
                    result = method(*worker_ctx.args, **worker_ctx.kwargs)
            except Exception as exc:
                if isinstance(exc, worker_ctx.entrypoint.expected_exceptions):
                    _log.warning(
                        "(预期的) 处理工作线程 %s 时发生错误: %s",
                        worker_ctx,
                        exc,
                        exc_info=True,
                    )
                else:
                    _log.exception("处理工作线程 %s 时发生错误: %s", worker_ctx, exc)
                exc_info = sys.exc_info()

            if handle_result is not None:
                _log.debug("处理结果 %s", worker_ctx)

                with _log_time("处理结果完成 %s", worker_ctx):
                    result, exc_info = handle_result(worker_ctx, result, exc_info)

            with _log_time("拆除工作线程 %s", worker_ctx):
                self._worker_result(worker_ctx, result, exc_info)

                # 我们不再需要这个，打破循环意味着
                # 这可以立即回收，而不是等待
                # 垃圾回收清扫
                del exc_info

                self._worker_teardown(worker_ctx)

    def _inject_dependencies(self, worker_ctx):
        for provider in self.dependencies:
            dependency = provider.get_dependency(worker_ctx)
            setattr(worker_ctx.service, provider.attr_name, dependency)

    def _worker_setup(self, worker_ctx):
        for provider in self.dependencies:
            provider.worker_setup(worker_ctx)

    def _worker_result(self, worker_ctx, result, exc_info):
        _log.debug("signalling result for %s", worker_ctx)
        for provider in self.dependencies:
            provider.worker_result(worker_ctx, result, exc_info)

    def _worker_teardown(self, worker_ctx):
        for provider in self.dependencies:
            provider.worker_teardown(worker_ctx)

    def _kill_worker_threads(self):
        """终止任何当前正在执行的工作线程。

        参见 :meth:`ServiceContainer.spawn_worker`
        """
        num_workers = len(self._worker_threads)

        if num_workers:
            _log.warning("正在终止 %s 个活跃工作线程", num_workers)
            for worker_ctx, gt in list(self._worker_threads.items()):
                _log.warning("正在终止 %s 的活跃工作线程", worker_ctx)
                gt.kill()

    def _kill_managed_threads(self):
        """终止任何当前正在执行的托管线程。

        参见 :meth:`ServiceContainer.spawn_managed_thread`
        """
        num_threads = len(self._managed_threads)

        if num_threads:
            _log.warning("正在终止 %s 个托管线程", num_threads)
            for gt, identifier in list(self._managed_threads.items()):
                _log.warning("正在终止托管线程 `%s`", identifier)
                gt.kill()

    def _handle_worker_thread_exited(self, gt, worker_ctx):
        self._worker_threads.pop(worker_ctx, None)
        self._handle_thread_exited(gt)

    def _handle_managed_thread_exited(self, gt, extension):
        self._managed_threads.pop(gt, None)
        self._handle_thread_exited(gt)

    def _handle_thread_exited(self, gt):
        try:
            gt.wait()

        except GreenletExit:
            # 我们对容器终止的线程不太在意
            # 这可能在 stop() 和 kill() 中发生，如果扩展
            # 没有正确处理它们的线程
            _log.debug("%s 线程被容器终止", self)

        except Exception:
            _log.critical("%s 线程以错误退出", self, exc_info=True)
            # 在线程中引发的任何未捕获错误都是意外行为
            # 可能是扩展或容器中的错误。
            # 为了安全起见，我们调用 self.kill() 来终止我们的依赖项，并
            # 提供在 self.wait() 中引发的异常信息。
            self.kill(sys.exc_info())

    def __repr__(self):
        service_name = self.service_name
        return "<ServiceContainer [{}] at 0x{:x}>".format(service_name, id(self))
