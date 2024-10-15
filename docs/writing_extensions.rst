.. _writing_extensions:

编写扩展
==================

结构(Structure)
-----------------

扩展应继承自 :class:`nameko.extensions.Extension` 。这个基类提供了扩展的基本结构，特别是以下方法，可以重写以添加功能:

.. sidebar:: Binding

    在服务类中的扩展仅仅是一个声明。当一个服务被 :ref:`服务容器 <containers>` :ref:`托管 <running_services>` 时，其扩展会“绑定”到容器。

    绑定过程对编写新扩展的开发人员是透明的。唯一需要考虑的是， :meth:`~nameko.extensions.Extension.__init__` 在 :meth:`~nameko.extensions.Extensions.bind` 中以及在服务类声明时都会被调用，因此应避免在该方法中产生副作用，而应使用 :meth:`~nameko.extensions.Extensions.setup` 。

.. automethod:: nameko.extensions.Extension.setup
    :no-index:

.. automethod:: nameko.extensions.Extension.start
    :no-index:

.. automethod:: nameko.extensions.Extension.stop
    :no-index:


编写依赖提供者
----------------------------

几乎每个 Nameko 应用程序都需要定义自己的依赖项——可能是为了与没有 :ref:`社区扩展 <community_extensions>` 的数据库接口，或与 :ref:`特定网络服务 <travis>` 进行通信。

依赖提供者应继承自 `nameko.extensions.DependencyProvider` 类，并实现一个 `~nameko.extensions.DependencyProvider.get_dependency` 方法，该方法返回要注入到服务工作者中的对象。

推荐的模式是注入依赖项所需的最小接口。这减少了测试的复杂性，并使在测试中更容易执行服务代码。

依赖提供者还可以挂钩到 *工作者生命周期*。以下三个方法会在每个工作者的所有依赖提供者上被调用：

.. automethod:: nameko.extensions.DependencyProvider.worker_setup
    :no-index:

.. automethod:: nameko.extensions.DependencyProvider.worker_result
    :no-index:

.. automethod:: nameko.extensions.DependencyProvider.worker_teardown
    :no-index:

并发与线程安全
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

`~nameko.extensions.DependencyProvider.get_dependency` 方法返回的对象应该是线程安全的，因为它可能被多个并发运行的工作者访问。

*工作者生命周期* 在执行服务方法的同一线程中被调用。这意味着，例如，你可以定义线程局部变量，并从每个方法中访问它们。


示例
^^^^^^^

一个简单的 ``DependencyProvider``，用于向 SQS 队列发送消息。

.. literalinclude:: examples/sqs_send.py


编写入口点
-------------------

如果你想支持新的传输或启动服务代码的机制，可以实现新的 Entrypoint 扩展。

Entrypoint 的最低要求是：

1. 继承自 :class:`nameko.extensions.Entrypoint`。
2. 实现 :meth:`~nameko.extensions.Entrypoint.start()` 方法，以便在容器启动时启动入口点。如果需要后台线程，建议使用由服务容器管理的线程（参见 :ref:`spawning_background_threads` ）。
3. 在适当的时候调用绑定容器上的 :meth:`~nameko.containers.ServiceContainer.spawn_worker()` 。

示例
^^^^^^^

一个简单的 ``Entrypoint``，用于从 SQS 队列接收消息。

.. literalinclude:: examples/sqs_receive.py

在一个服务中使用:

.. literalinclude:: examples/sqs_service.py

预期异常
^^^^^^^^^^^^^^^^^^^

Entrypoint 基类构造函数将接受一个类列表，这些类在被装饰的服务方法中被引发时应被视为“预期的”。这可以用于区分 *用户错误* 和更根本的执行错误。例如：

.. literalinclude:: examples/expected_exceptions.py
    :pyobject: Service

预期异常的列表会保存到 Entrypoint 实例中，以便稍后进行检查，例如通过其他处理异常的扩展，如 `nameko-sentry <https://github.com/mattbennett/nameko-sentry/blob/b254ba99df5856030dfcb1d13b14c1c8a41108b9/nameko_sentry.py#L159-L164>`_ 。


敏感参数
^^^^^^^^^^^^^^^^^^^

与 *预期异常* 类似，Entrypoint 构造函数允许你将某些参数或参数部分标记为敏感。例如：

.. literalinclude:: examples/sensitive_arguments.py
    :pyobject: Service

这可以与实用函数 `nameko.utils.get_redacted_args` 结合使用，该函数将返回入口点的调用参数（类似于 `inspect.getcallargs` ），但敏感元素被遮蔽。

这在记录或保存有关入口点调用信息的扩展中非常有用，例如 `nameko-tracer <https://github.com/Overseas-Student-Living/nameko-tracer>`_ 。

对于接受嵌套在其他安全参数中的敏感信息的入口点，可以指定部分遮蔽。例如：

.. code-block:: python

    # by dictionary key
    @entrypoint(sensitive_arguments="foo.a")
    def method(self, foo):
        pass

    >>> get_redacted_args(method, foo={'a': 1, 'b': 2})
    ... {'foo': {'a': '******', 'b': 2}}

    # list index
    @entrypoint(sensitive_arguments="foo.a[1]")
    def method(self, foo):
        pass

    >>> get_redacted_args(method, foo=[{'a': [1, 2, 3]}])
    ... {'foo': {'a': [1, '******', 3]}}


不支持切片和相对列表索引。

.. _spawning_background_threads:

生成后台线程
---------------------------

需要在线程中执行工作的扩展可以选择通过使用 :meth:`~nameko.containers.ServiceContainer.spawn_managed_thread()` 将该线程的管理委托给服务容器。

.. literalinclude:: examples/sqs_receive.py
    :pyobject: SqsReceive.start

建议将线程管理委托给容器，因为：

* 管理的线程在容器停止或被杀死时会始终被终止。
* 管理线程中的未处理异常会被容器捕获，并导致其终止并显示适当的消息，这可以防止进程挂起。
