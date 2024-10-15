from __future__ import unicode_literals

import inspect
import sys

import six


if sys.version_info >= (3, 3):  # pragma: no cover
    from collections.abc import Iterable  # pylint: disable=E0611,E0401
else:  # pragma: no cover
    from collections import Iterable


class ExtensionNotFound(AttributeError):
    pass


class RpcTimeout(Exception):
    pass


class ReplyQueueExpiredWithPendingReplies(Exception):
    pass


class ContainerBeingKilled(Exception):
    """在 :meth:`Container.spawn_worker` 启动 ``kill`` 序列时引发。

    入口点应捕获此异常，并作出反应，仿佛它们一开始就不可用，例如，RPC 消费者可能应重新排队该消息。

    我们需要这个，因为在执行 :meth:`Container.kill` 时，Eventlet 可能会让出控制权，从而使入口点在它们自己被杀死之前有机会执行。
    """


registry = {}


def get_module_path(exc_type):
    """返回 `exc_type` 的点分模块路径，包括类名。

    e.g.::

        >>> get_module_path(MethodNotFound)
        >>> "nameko.exceptions.MethodNotFound"

    """
    module = inspect.getmodule(exc_type)
    return "{}.{}".format(module.__name__, exc_type.__name__)


class RemoteError(Exception):
    """如果远程工作者发生异常，则在调用者处引发的异常。"""

    def __init__(self, exc_type=None, value=""):
        self.exc_type = exc_type
        self.value = value
        message = "{} {}".format(exc_type, value)
        super(RemoteError, self).__init__(message)


def safe_for_serialization(value):
    """在准备将值序列化为 JSON 时进行转换。

    对于字符串，映射和可迭代对象不进行操作，其条目被处理为安全；对于所有其他值，进行字符串化，如果失败则使用回退值。
    """

    if isinstance(value, six.string_types):
        return value
    if isinstance(value, dict):
        return {
            safe_for_serialization(key): safe_for_serialization(val)
            for key, val in six.iteritems(value)
        }
    if isinstance(value, Iterable):
        return list(map(safe_for_serialization, value))

    try:
        return six.text_type(value)
    except Exception:
        return "[__unicode__ failed]"


def serialize(exc):
    """将 `self.exc` 序列化为表示它的数据字典。"""

    return {
        "exc_type": type(exc).__name__,
        "exc_path": get_module_path(type(exc)),
        "exc_args": list(map(safe_for_serialization, exc.args)),
        "value": safe_for_serialization(exc),
    }


def deserialize(data):
    """将 `data` 反序列化为异常实例。

    如果 `exc_path` 值与注册为“可反序列化”的异常匹配，则返回该异常类型的实例。否则，返回一个描述发生异常的 `RemoteError` 实例。
    """
    key = data.get("exc_path")
    if key in registry:
        exc_args = data.get("exc_args", ())
        return registry[key](*exc_args)

    exc_type = data.get("exc_type")
    value = data.get("value")
    return RemoteError(exc_type=exc_type, value=value)


def deserialize_to_instance(exc_type):
    """装饰器，将 `exc_type` 注册为可反序列化为实例，而不是 :class:`RemoteError`。参见 :func:`deserialize`。"""
    key = get_module_path(exc_type)
    registry[key] = exc_type
    return exc_type


class BadRequest(Exception):
    pass


@deserialize_to_instance
class MalformedRequest(BadRequest):
    pass


@deserialize_to_instance
class MethodNotFound(BadRequest):
    pass


@deserialize_to_instance
class IncorrectSignature(BadRequest):
    pass


class UnknownService(Exception):
    def __init__(self, service_name):
        self._service_name = service_name
        super(UnknownService, self).__init__(service_name)

    def __str__(self):
        return "Unknown service `{}`".format(self._service_name)


class UnserializableValueError(Exception):
    def __init__(self, value):
        try:
            self.repr_value = repr(value)
        except Exception:
            self.repr_value = "[__repr__ failed]"
        super(UnserializableValueError, self).__init__()

    def __str__(self):
        return "Unserializable value: `{}`".format(self.repr_value)


class ConfigurationError(Exception):
    pass


class CommandError(Exception):
    """从子命令中引发，以将错误报告回用户。"""


class ConnectionNotFound(BadRequest):
    """Unknown websocket connection id"""
