测试服务
================

哲学
----------

Nameko 的约定旨在使测试尽可能简单。服务通常是小型且单一用途的，而依赖注入则使得替换和隔离功能模块变得简单。

以下示例使用 `pytest <http://pytest.org/latest/>`_ ，这是 Nameko 自身测试套件所使用的，但这些辅助工具与测试框架无关。

单元测试
------------

在 Nameko 中，单元测试通常意味着在隔离环境中测试单个服务——换句话说，不依赖于任何或大部分依赖项。

:func:`~nameko.testing.services.worker_factory` 工具将从给定的服务类创建一个 worker，其依赖项被 :class:`mock.MagicMock` 对象替代。然后可以通过添加 :attr:`~mock.Mock.side_effect` 和 :attr:`~mock.Mock.return_value` 来模拟依赖功能：

.. literalinclude:: examples/testing/unit_test.py

在某些情况下，提供替代依赖项而不是使用 mock 是有帮助的。这可以是一个完全功能的替代品（例如，测试数据库会话），或是一个提供部分功能的轻量级适配器。

.. literalinclude:: examples/testing/alternative_dependency_unit_test.py

集成测试
-------------------

在 Nameko 中，集成测试意味着测试多个服务之间的接口。推荐的方法是以正常方式运行所有被测试的服务，并通过使用助手“触发”一个入口点来引发行为：

.. literalinclude:: examples/testing/integration_test.py

请注意，这里 ``ServiceX`` 和 ``ServiceY`` 之间的接口就像在正常操作下一样。

对于特定测试不在范围内的接口，可以使用以下测试助手之一来禁用：

限制入口点
^^^^^^^^^^^^^^^^^^^^

.. autofunction:: nameko.testing.services.restrict_entrypoints
   :noindex:

替换依赖项
^^^^^^^^^^^^^^^^^^^^

.. autofunction:: nameko.testing.services.replace_dependencies
   :noindex:

完整示例
^^^^^^^^^^^^^^^^

以下集成测试示例使用了两个作用域限制助手：

.. literalinclude:: examples/testing/large_integration_test.py

其他助手
-------------

入口点钩子
^^^^^^^^^^^^^^^

入口点钩子允许手动调用服务入口点。这在集成测试中非常有用，特别是当很难或昂贵地模拟导致入口点被触发的外部事件时。

您可以为调用提供 `context_data` ，以模拟特定的调用上下文，例如语言、用户代理或身份验证令牌。

.. literalinclude:: examples/testing/entrypoint_hook_test.py

入口点等待器
^^^^^^^^^^^^^^^^^

入口点等待器是一个上下文管理器，直到指定的入口点被触发并完成时才会退出。这在测试服务之间的异步集成点时非常有用，例如接收事件：

.. literalinclude:: examples/testing/entrypoint_waiter_test.py

请注意，该上下文管理器不仅等待入口点方法的完成，还等待任何依赖项的拆解。例如，基于依赖项的日志记录器（TODO: 链接到捆绑的日志记录器）也会完成。

使用 pytest
------------

Nameko 的测试套件使用 pytest，并为您选择使用 pytest 时提供一些有用的配置和固件。

它们包含在 :mod:`nameko.testing.pytest` 中。该模块作为 `pytest 插件 <https://docs.pytest.org/en/latest/plugins.html>`_ 通过 setuptools 注册。Pytest 会自动识别并使用它。
