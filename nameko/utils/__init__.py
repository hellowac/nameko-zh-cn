import inspect
import re
from copy import deepcopy
from pydoc import locate

from typing import Any

import six
from six.moves.urllib.parse import urlparse


REDACTED = "********"


def get_redacted_args(entrypoint, *args, **kwargs):
    """
    用于与标记为 ``sensitive_arguments`` 的入口点配合使用的实用函数，例如： :class:`nameko.rpc.Rpc` 和 :class:`nameko.events.EventHandler`。

    :Parameters:

        entrypoint : :class:`~nameko.extensions.Entrypoint`
            被触发的入口点。
        args : tuple
            方法调用的位置参数。
        kwargs : dict
            方法调用的关键字参数。

    入口点应该具有 ``sensitive_arguments`` 属性，其值是一个字符串或字符串元组，指定应该被隐去的参数或部分参数。如果要部分隐去某个参数，使用以下语法::

        <argument-name>.<dict-key>[<list-index>]

    :Returns:

        返回一个字典，由 :func:`inspect.getcallargs` 返回，但敏感参数或部分参数已被隐去。

    .. note::

        如果其中一个 ``sensitive_arguments`` 与调用的 ``args`` 和 ``kwargs`` 不匹配或部分匹配，该函数不会引发异常。
        这允许进行“模糊”模式匹配（例如，如果存在字段，则隐去该字段，否则不执行任何操作）。

        为了避免因拼写错误而泄露敏感参数，建议单独测试每个具有 ``sensitive_arguments`` 的入口点的配置。例如：

        .. code-block:: python

            class Service(object):
                @rpc(sensitive_arguments="foo.bar")
                def method(self, foo):
                    pass

            container = ServiceContainer(Service, {})
            entrypoint = get_extension(container, Rpc, method_name="method")

            # no redaction
            foo = "arg"
            expected_foo = {'foo': "arg"}
            assert get_redacted_args(entrypoint, foo) == expected

            # 'bar' key redacted
            foo = {'bar': "secret value", 'baz': "normal value"}
            expected = {'foo': {'bar': "********", 'baz': "normal value"}}
            assert get_redacted_args(entrypoint, foo) == expected

    .. seealso::

        该实用程序的测试演示了其完整用法： :class:`test.test_utils.TestGetRedactedArgs` 。
    """
    sensitive_arguments = entrypoint.sensitive_arguments
    if isinstance(sensitive_arguments, six.string_types):
        sensitive_arguments = (sensitive_arguments,)

    method = getattr(entrypoint.container.service_cls, entrypoint.method_name)
    callargs = inspect.getcallargs(method, None, *args, **kwargs)
    del callargs["self"]

    # make a deepcopy before redacting so that "partial" redacations aren't applied to a referenced object

    # 在进行敏感参数隐去之前，先执行深拷贝，以确保“部分”隐去不会应用于被引用的对象。
    callargs = deepcopy(callargs)

    def redact(data, keys):
        key = keys[0]
        if len(keys) == 1:
            try:
                data[key] = REDACTED
            except (KeyError, IndexError, TypeError):
                pass
        else:
            if key in data:
                redact(data[key], keys[1:])

    for variable in sensitive_arguments:
        keys = []
        for dict_key, list_index in re.findall(r"(\w+)|\[(\d+)\]", variable):
            if dict_key:
                keys.append(dict_key)
            elif list_index:
                keys.append(int(list_index))

        if keys[0] in callargs:
            redact(callargs, keys)

    return callargs


def import_from_path(path) -> Any:
    """如果对象在 `path` 中存在，则导入并返回该对象。

    如果未找到该对象，则引发 `ImportError`。
    """
    if path is None:
        return

    obj = locate(path)
    if obj is None:
        raise ImportError("`{}` could not be imported".format(path))

    return obj


def sanitize_url(url):
    """在 URLs 中隐藏密码。"""
    parts = urlparse(url)
    if parts.password is None:
        return url
    host_info = parts.netloc.rsplit("@", 1)[-1]
    parts = parts._replace(
        netloc="{}:{}@{}".format(parts.username, REDACTED, host_info)
    )
    return parts.geturl()
