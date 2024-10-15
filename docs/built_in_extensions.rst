.. _built_in_extensions:

内置扩展
===================

Nameko 包含多个内置的 :ref:`扩展 <extensions>` 。本节介绍这些扩展并给出它们用法的简要示例。

RPC
---

Nameko 包含一个基于 AMQP 的 RPC 实现。它包括 ``@rpc`` 入口点，一个服务间通信的代理，以及一个独立的代理，非 Nameko 客户端可以使用它来向集群发起 RPC 调用：

.. literalinclude:: examples/rpc.py

.. literalinclude:: examples/standalone_rpc.py

正常的 RPC 调用会阻塞，直到远程方法完成，但代理也具有异步调用模式，可以将 RPC 调用后台执行或并行化：

.. literalinclude:: examples/async_rpc.py

在具有多个目标服务实例的集群中，RPC 请求会在实例之间进行轮询。请求将由目标服务的一个实例处理。

只有在请求成功处理后，AMQP 消息才会被确认。如果服务未能确认消息并且 AMQP 连接关闭（例如，如果服务进程被终止），则代理会撤销并将消息分配给可用的服务实例。

请求和响应负载会序列化为 JSON 格式，以便通过网络传输。

事件 (发布-订阅)
----------------

Nameko 事件是一个异步消息系统，实现了发布-订阅模式。服务会分发事件，这些事件可能会被零个或多个其他服务接收：

.. literalinclude:: examples/events.py

:class:`~nameko.events.EventHandler` 入口点有三种 ``handler_type``\s ，它们决定了事件消息在集群中是如何接收的：

* ``SERVICE_POOL`` — 事件处理程序按服务名称进行分组，每个池中的一个实例接收事件，类似于 RPC 入口点的集群行为。这是默认的处理程序类型。
* ``BROADCAST`` — 每个监听的服务实例都将接收该事件。
* ``SINGLETON`` — 精确一个监听的服务实例将接收该事件。

使用 ``BROADCAST`` 模式的示例：

.. literalinclude:: examples/event_broadcast.py

事件会序列化为 JSON 格式，以便通过网络传输。

HTTP
---------------

HTTP 入口点是基于 `werkzeug <http://werkzeug.pocoo.org/>`_ 构建的，支持所有标准 HTTP 方法（GET/POST/DELETE/PUT 等）。

HTTP 入口点可以为单个 URL 指定多个 HTTP 方法，使用逗号分隔的列表。请参见下面的示例。

服务方法必须返回以下之一：

- 一个字符串，作为响应体
- 一个 2 元组 ``(状态码, 响应体)``
- 一个 3 元组 ``(状态码, 头部字典, 响应体)``
- 一个 :class:`werkzeug.wrappers.Response` 的实例

.. literalinclude:: examples/http.py

.. code-block:: shell

    $ nameko run http
    starting services: http_service

.. code-block:: shell

    $ curl -i localhost:8000/get/42
    HTTP/1.1 200 OK
    Content-Type: text/plain; charset=utf-8
    Content-Length: 13
    Date: Fri, 13 Feb 2015 14:51:18 GMT

    {'value': 42}

.. code-block:: shell

    $ curl -i -d "post body" localhost:8000/post
    HTTP/1.1 200 OK
    Content-Type: text/plain; charset=utf-8
    Content-Length: 19
    Date: Fri, 13 Feb 2015 14:55:01 GMT

    received: post body

一个高级用法示例:

.. literalinclude:: examples/advanced_http.py

.. code-block:: shell

    $ nameko run advanced_http
    starting services: advanced_http_service

.. code-block:: shell

    $ curl -i localhost:8000/privileged
    HTTP/1.1 403 FORBIDDEN
    Content-Type: text/plain; charset=utf-8
    Content-Length: 9
    Date: Fri, 13 Feb 2015 14:58:02 GMT

.. code-block:: shell

    curl -i localhost:8000/headers
    HTTP/1.1 201 CREATED
    Location: https://www.example.com/widget/1
    Content-Type: text/plain; charset=utf-8
    Content-Length: 0
    Date: Fri, 13 Feb 2015 14:58:48 GMT


您可以通过重写 :meth:`~nameko.web.HttpRequestHandler.response_from_exception` 来控制从您的服务返回的错误格式：

.. literalinclude:: examples/http_exceptions.py

.. code-block:: shell

    $ nameko run http_exceptions
    starting services: http_service

.. code-block:: shell

    $ curl -i http://localhost:8000/custom_exception
    HTTP/1.1 400 BAD REQUEST
    Content-Type: application/json
    Content-Length: 72
    Date: Thu, 06 Aug 2015 09:53:56 GMT

    {"message": "Argument `foo` is required.", "error": "INVALID_ARGUMENTS"}

你可以通过配置中的 `WEB_SERVER_ADDRESS` 来改变 HTTP 的端口和IP地址:

.. code-block:: yaml

    # foobar.yaml

    AMQP_URI: 'pyamqp://guest:guest@localhost'
    WEB_SERVER_ADDRESS: '0.0.0.0:8000'

计时器
--------

:class:`~nameko.timers.Timer` 是一个简单的入口点，它会每隔可配置的秒数触发一次。该计时器不是“集群感知”的，会在所有服务实例上触发。

.. literalinclude:: examples/timer.py
