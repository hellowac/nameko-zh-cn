"""
Nameko 组件可以作为独立工具使用，而无需托管在 Nameko 管理的服务内部。

旨在作为测试工具和外部控制使用，例如在 Nameko 集群中发起某些操作。

.. Example:

    使用 RPC 代理对 "mathsservice" 执行加法运算::

        >>> from nameko.standalone.rpc import rpc_proxy
        >>>
        >>> with rpc_proxy("mathsservice", config) as proxy:
        ...     result = proxy.add(2, 2)
        ...
        >>> print(result)
        4

.. Example:

    作为 ``srcservice`` 派发 ``custom_event``::

    >>> from nameko.standalone.events import event_dispatcher
    >>>
    >>> with event_dispatcher("srcservice", config) as dispatch:
    ...     dispatch("custom_event", "msg")
    ...
    >>>

"""
