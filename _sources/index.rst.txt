:orphan:

Nameko
======

*[nah-meh-koh]*

.. pull-quote ::

    一个用于 Python 的微服务框架，帮助服务开发者专注于应用逻辑并促进可测试性。

一个nameko服务仅仅是一个类:

.. code-block:: python

    # helloworld.py

    from nameko.rpc import rpc

    class GreetingService:
        name = "greeting_service"

        @rpc
        def hello(self, name):
            return "Hello, {}!".format(name)

.. note::

    上述示例需要使用 `RabbitMQ <https://www.rabbitmq.com>`_ ，因为它利用了内置的 AMQP RPC 功能。 `RabbitMQ 安装指南 <https://www.rabbitmq.com/download.html>`_ 提供了多种安装选项，但你可以使用 `Docker <https://docs.docker.com/install/>`_ 快速安装和运行 RabbitMQ。

    使用 Docker 安装并运行 RabbitMQ：

    .. code-block:: shell

       $ docker run -d -p 5672:5672 rabbitmq:3

    | *你可能需要使用 sudo 执行该命令。*

你可以在 shell 中运行它：

.. code-block:: shell

    $ nameko run helloworld
    starting services: greeting_service
    ...

然后在另一个 shell 中使用它：

.. code-block:: pycon

    $ nameko shell
    >>> n.rpc.greeting_service.hello(name="ナメコ")
    'Hello, ナメコ!'

目录
----------

本节涵盖创建和运行自己的 Nameko 服务所需了解的大部分内容。

.. toctree::
   :maxdepth: 2
   :caption: 用户指南

   what_is_nameko
   key_concepts
   installation
   cli
   built_in_extensions
   built_in_dependency_providers
   community_extensions
   testing
   writing_extensions
   examples/index
   apidoc

.. toctree::
   :maxdepth: 2
   :caption: 更多信息

   about_microservices
   dependency_injection_benefits
   similar_projects
   getting_in_touch
   contributing
   license
   release_notes


.. toctree::
   :hidden:
   :caption: 项目链接

   GitHub <https://github.com/nameko/nameko>
   GitHub 中文文档项目 <https://github.com/hellowac/nameko-zh-cn>
   readthedocs 英文文档 <https://nameko.readthedocs.io/en/stable/>
   Website <https://www.nameko.io//>


索引表
==================

* :ref:`genindex`
* :ref:`search`