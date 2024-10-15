from __future__ import absolute_import, annotations

import inspect
import types
import warnings
import weakref
from functools import partial
from logging import getLogger
from typing import Any, Type

from eventlet.event import Event

from nameko.exceptions import IncorrectSignature


_log = getLogger(__name__)


ENTRYPOINT_EXTENSIONS_ATTR = "nameko_entrypoints"


class Extension(object):
    """请注意，`Extension.__init__` 在 `bind` 过程中以及实例化时都会被调用，因此请避免在此方法中产生副作用。请使用 `setup`。

    此外，`bind` 和 `iter_extensions` 使用反射来查找扩展可能声明的任何子扩展。扩展上的任何描述符应该预计在反射过程中被调用，这发生在 `ServiceContainer.__init__` 和 `ServiceContainer.setup` 之间。

    `Extension.container` 属性提供对绑定到该扩展的 `nameko.containers.ServiceContainer` 实例的访问，否则为 `None`。
    """

    __params = None
    container = None

    def __new__(cls, *args, **kwargs):
        inst = super(Extension, cls).__new__(cls)
        inst.__params = (args, kwargs)
        return inst

    def setup(self):
        """在容器启动之前调用了绑定的扩展。

        扩展应在此处进行任何必要的初始化。
        """

    def start(self):
        """在容器成功启动时调用绑定的扩展。

        此方法仅在所有其他扩展成功返回 `Extension.setup` 后被调用。如果扩展对外部事件做出反应，它现在应该开始对此进行响应。
        """

    def stop(self):
        """在服务容器开始关闭时调用。

        扩展应在此处执行任何优雅的关闭操作。
        """

    def kill(self):
        """在没有优雅关闭的情况下调用以停止此扩展。

        扩展应在此处紧急关闭。这意味着尽快停止，省略清理操作。对于某些依赖项，这可能与 `stop()` 不同。

        例如，`messaging.QueueConsumer` 类跟踪正在处理的消息和待处理的消息确认。它的 `kill` 实现会尽快丢弃这些消息并与 Rabbit 断开连接。

        在执行 kill 时，扩展不应引发异常，因为容器已经在关闭。相反，它们应该记录适当的信息，并捕获异常，以允许容器继续关闭。
        """

    def bind(self, container):
        """获取当前扩展的实例绑定到 `container`."""

        import nameko.containers

        container: nameko.containers.ServiceContainer

        def clone(prototype):
            if prototype.is_bound():
                raise RuntimeError("无法从一个已绑定的扩展进行 `bind`。")

            cls = type(prototype)
            args, kwargs = prototype.__params
            instance = cls(*args, **kwargs)
            # instance.container 必须是一个弱引用，以避免在 `shared_extensions` 的 weakkey 字典中
            # 从值到键的强引用
            # 参见 test_extension_sharing.py: test_weakref
            instance.container = weakref.proxy(container)
            return instance

        instance = clone(self)

        # recurse over sub-extensions
        for name, ext in inspect.getmembers(self, is_extension):
            setattr(instance, name, ext.bind(container))
        return instance

    def is_bound(self):
        return self.container is not None

    def __repr__(self):
        if not self.is_bound():
            return "<{} [unbound] at 0x{:x}>".format(type(self).__name__, id(self))

        return "<{} at 0x{:x}>".format(type(self).__name__, id(self))


class SharedExtension(Extension):
    @property
    def sharing_key(self):
        return type(self)

    def bind(self, container):
        """支持共享的绑定实现。"""
        # 如果已经存在匹配的绑定实例，返回该实例
        shared = container.shared_extensions.get(self.sharing_key)
        if shared:
            return shared

        instance = super(SharedExtension, self).bind(container)

        # 保存新的实例
        container.shared_extensions[self.sharing_key] = instance

        return instance


class DependencyProvider(Extension):
    attr_name = None


    def bind(self, container, attr_name: str):
        """获取一个依赖项的实例，以便与 `container` 和 `attr_name` 绑定。"""
        
        instance = super(DependencyProvider, self).bind(container)
        instance.attr_name = attr_name
        self.attr_name = attr_name
        return instance

    def get_dependency(self, worker_ctx):
        """在工作者执行之前调用。依赖提供者应返回一个对象，以便容器将其注入到工作者实例中。"""

    def worker_result(self, worker_ctx, result=None, exc_info=None):
        """在服务工作者执行结果时调用。

        需要处理结果的依赖项应在此处进行处理。此方法在任何工作者完成时会被调用所有 `Dependency` 实例。

        示例：数据库会话依赖项可能会刷新事务。

        :Parameters:
            worker_ctx : :class:`~nameko.containers.WorkerContext`
                见 :meth:`~nameko.containers.ServiceContainer.spawn_worker`
        """

    def worker_setup(self, worker_ctx):
        """在服务工作者执行任务之前调用。

        依赖项应在此处进行任何预处理，如果失败则引发异常。

        Example: ...

        :Parameters:
            worker_ctx : :class:`~nameko.containers.WorkerContext`
                见 :meth:`~nameko.containers.ServiceContainer.spawn_worker`
        """

    def worker_teardown(self, worker_ctx):
        """在服务工作者执行完任务后调用。

        依赖项应在此处进行任何后处理，如果失败则引发异常。

        示例：数据库会话依赖项可能会提交会话。

        :Parameters:
            worker_ctx : :class:`~nameko.containers.WorkerContext`
                见 :meth:`~nameko.containers.ServiceContainer.spawn_worker`
        """

    def __repr__(self):
        if not self.is_bound():
            return "<{} [unbound] at 0x{:x}>".format(type(self).__name__, id(self))

        service_name = self.container.service_name
        return "<{} [{}.{}] at 0x{:x}>".format(
            type(self).__name__, service_name, self.attr_name, id(self)
        )


class ProviderCollector(object):
    def __init__(self, *args, **kwargs):
        self._providers = set()
        self._providers_registered = False
        self._last_provider_unregistered = Event()
        super(ProviderCollector, self).__init__(*args, **kwargs)

    def register_provider(self, provider):
        self._providers_registered = True
        _log.debug("registering provider %s for %s", provider, self)
        self._providers.add(provider)

    def unregister_provider(self, provider):
        providers = self._providers
        if provider not in self._providers:
            return

        _log.debug("unregistering provider %s for %s", provider, self)

        providers.remove(provider)
        if len(providers) == 0:
            _log.debug("last provider unregistered for %s", self)
            self._last_provider_unregistered.send()

    def wait_for_providers(self):
        """等待与收集器注册的任何提供者注销。

        如果没有提供者被注册，则立即返回。
        """
        if self._providers_registered:
            _log.debug("正在等待提供者注销 %s", self)
            self._last_provider_unregistered.wait()
            _log.debug("所有提供者已注销 %s", self)

    def stop(self):
        """使用 `ProviderCollector` 作为混入类的子类的默认 `:meth:Extension.stop()` 实现。"""
        self.wait_for_providers()


def register_entrypoint(fn, entrypoint):
    descriptors = getattr(fn, ENTRYPOINT_EXTENSIONS_ATTR, None)

    if descriptors is None:
        descriptors = set()
        setattr(fn, ENTRYPOINT_EXTENSIONS_ATTR, descriptors)

    descriptors.add(entrypoint)


class Entrypoint(Extension):
    method_name = None

    def __init__(self, expected_exceptions=(), sensitive_arguments=(), **kwargs):
        """
        :Parameters:
            expected_exceptions : 异常类或异常类元组
                指定可能由调用者引起的异常（例如，通过提供错误的参数）。
                保存在入口点实例中作为 ``entrypoint.expected_exceptions``，供其他扩展（例如监控系统）后续检查。
            sensitive_arguments : 字符串或字符串元组
                将参数或参数的一部分标记为敏感。保存在入口点实例中作为 ``entrypoint.sensitive_arguments``，
                供其他扩展（例如日志系统）后续检查。

                :seealso: :func:`nameko.utils.get_redacted_args`
        """
        # 向后兼容
        sensitive_variables = kwargs.pop("sensitive_variables", ())
        if sensitive_variables:
            sensitive_arguments = sensitive_variables
            warnings.warn(
                "参数 `sensitive_variables` 已重命名为 "
                "`sensitive_arguments`。该警告将在 "
                "2.9.0 版本中删除。",
                DeprecationWarning,
            )

        self.expected_exceptions = expected_exceptions
        self.sensitive_arguments = sensitive_arguments
        super(Entrypoint, self).__init__(**kwargs)

    def bind(self, container, method_name):
        """获取此入口点的实例，以便与 `method_name` 绑定到 `container`。"""
        instance = super(Entrypoint, self).bind(container)
        instance.method_name = method_name
        return instance

    def check_signature(self, args, kwargs):
        service_cls = self.container.service_cls
        fn = getattr(service_cls, self.method_name)
        try:
            service_instance = None  # fn is unbound
            inspect.getcallargs(fn, service_instance, *args, **kwargs)
        except TypeError as exc:
            raise IncorrectSignature(str(exc))

    @classmethod
    def decorator(cls, *args, **kwargs):
        def registering_decorator(fn, args, kwargs):
            instance = cls(*args, **kwargs)
            register_entrypoint(fn, instance)
            return fn

        if len(args) == 1 and isinstance(args[0], types.FunctionType):
            # usage without arguments to the decorator:
            # @foobar
            # def spam():
            #     pass
            return registering_decorator(args[0], args=(), kwargs={})
        else:
            # usage with arguments to the decorator:
            # @foobar('shrub', ...)
            # def spam():
            #     pass
            return partial(registering_decorator, args=args, kwargs=kwargs)

    def __repr__(self):
        if not self.is_bound():
            return "<{} [unbound] at 0x{:x}>".format(type(self).__name__, id(self))

        service_name = self.container.service_name
        return "<{} [{}.{}] at 0x{:x}>".format(
            type(self).__name__, service_name, self.method_name, id(self)
        )


def is_extension(obj: Any):
    return isinstance(obj, Extension)


def is_dependency(obj: Any):
    return isinstance(obj, DependencyProvider)


def is_entrypoint(obj: Any):
    return isinstance(obj, Entrypoint)


def iter_extensions(extension):
    """对 `extension` 的子扩展进行深度优先迭代器。"""
    for _, ext in inspect.getmembers(extension, is_extension):
        for item in iter_extensions(ext):
            yield item
        yield ext
