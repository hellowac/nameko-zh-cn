Nameko
======

.. image:: https://github.com/nameko/nameko/actions/workflows/ci.yaml/badge.svg

`English <https://github.com/nameko/nameko>`_

*[nah-meh-koh]*

.. pull-quote::

    一个为 Python 设计的微服务框架，让服务开发者专注于应用逻辑并鼓励可测试性。

Nameko 服务只是一个类：

.. code-block:: python

    # helloworld.py

    from nameko.rpc import rpc

    class GreetingService:
        name = "greeting_service"

        @rpc
        def hello(self, name):
            return "Hello, {}!".format(name)

你可以在 shell 中运行它：

.. code-block:: shell

    $ nameko run helloworld
    starting services: greeting_service
    ...

并在另一个 shell 中与它交互：

.. code-block:: pycon

    $ nameko shell
    >>> n.rpc.greeting_service.hello(name="ナメコ")
    'Hello, ナメコ!'

功能
--------

* AMQP RPC 和事件（发布-订阅模式）
* HTTP GET、POST 和 websockets
* 提供易于快速开发的命令行工具
* 单元测试和集成测试的工具

入门指南
---------------

* 查看 `文档 <https://hellowac.github.io/nameko-zh-cn/>`_ 。


编辑文档
_____________________

要在浏览器中快速查看文档，请尝试：

.. code-block:: bash

    nox -s docs -- serve

支持
-------

如需帮助、评论或有疑问，请访问 `<https://discourse.nameko.io/>`_ 。

企业支持
---------------------

可作为 Tidelift 订阅的一部分。

Nameko 的维护者和成千上万的其他开源包维护者与 Tidelift 合作，提供您用于构建应用程序的开源依赖项的商业支持和维护服务。节省时间、降低风险、改善代码健康状况，同时支持您实际使用的依赖项的维护者。`了解更多。<https://tidelift.com/subscription/pkg/pypi-nameko?utm_source=pypi-nameko&utm_medium=referral&utm_campaign=enterprise&utm_term=repo>`_

安全联系人信息
----------------------------

如需报告安全漏洞，请使用 `Tidelift 安全联系 <https://tidelift.com/security>`_ 。Tidelift 将协调修复和披露。

贡献
----------

* Fork 代码仓库
* 提出问题或功能请求

许可证
-------

Apache 2.0。详情请参阅 LICENSE 文件。