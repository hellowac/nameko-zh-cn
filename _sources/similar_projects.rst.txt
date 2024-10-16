类似和相关项目
============================

Celery
------

`Celery <http://celery.readthedocs.io/>`_ 是一个分布式任务队列。它允许你将“任务”定义为 Python 函数，并在一组远程工作者上执行它们，这与 Nameko RPC 有些相似。

Celery 通常用作现有应用程序的附加组件，以延迟处理或将某些工作外包给远程机器。你也可以通过 Nameko 实现这一点，但 Celery 包含了更多用于任务分配和结果收集的基本功能。

Zato
----

`Zato <http://zato.io>`_ 是一个用 Python 编写的完整 `企业服务总线 <http://en.wikipedia.org/wiki/Enterprise_service_bus>`_ (ESB) 和应用服务器。它专注于将许多不同的服务结合在一起，包括 API 和配置的 GUI。它还包括负载均衡和部署的工具。

ESB 通常用作旧服务之间的中间件。你可以在 Zato 中编写新的 Python 服务，但它们的结构截然不同，并且其范围远大于 Nameko。有关 ESB 的比较，请参见马丁·福勒关于 `微服务 <http://martinfowler.com/articles/microservices.html#MicroservicesAndSoa>`_ 的论文。

Kombu
-----

`Kombu <http://kombu.readthedocs.io/>`_ 是一个 Python 消息库，Celery 和 Nameko 都在使用。它提供了 AMQP 的高层接口，并支持“虚拟”传输，因此可以与 Redis、ZeroMQ 和 MongoDB 等非 AMQP 传输一起运行。

Nameko 的 AMQP 特性是基于 Kombu 构建的，但不支持“虚拟”传输。

此外，由于使用 `eventlet <http://eventlet.net/>`_ 实现绿色并发(green concurrency)，Nameko 无法利用 Kombu 默认情况下使用的 C 扩展，例如 `librabbitmq <https://pypi.python.org/pypi/librabbitmq>`_ 。如果你希望在环境中出于其他目的使用 `librabbitmq <https://pypi.python.org/pypi/librabbitmq>`_ ，可以通过将代理 URL 定义为 ``pyamqp://`` 而不是 ``amqp://`` 强制 Kombu 使用标准 Python 实现的 AMQP。

Eventlet
--------

`Eventlet <http://eventlet.net/>`_ 是一个 Python 库，通过“绿线程”提供并发。你可以在 :ref:`Concurrency <concurrency>` 部分查看 Nameko 如何使用它的更多细节。