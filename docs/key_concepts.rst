关键概念
============

本节介绍 Nameko 的核心概念。

服务结构
--------------------

Nameko 服务只是一个 Python 类。类的方法封装了应用程序逻辑，并将任何 :ref:`依赖项 <dependencies>` 声明为属性。

通过 :ref:`入口点 <entrypoints>` 装饰器，方法向外界公开。

.. literalinclude:: examples/anatomy.py

.. _entrypoints:

入口点
^^^^^^^^^^^

入口点是服务方法的访问通道。它们通常监控外部实体，例如消息队列。当相关事件发生时，入口点可能会“触发”，然后由服务 :ref:`worker <workers>` 执行被装饰的方法。

.. _dependencies:

依赖项
^^^^^^^^^^^^

大多数服务依赖于自身以外的事物。Nameko 鼓励将这些事物实现为依赖项。

依赖项是隐藏不属于核心服务逻辑的代码的好机会。依赖项与服务的接口应尽可能简单。

在服务中声明依赖项是一个好主意，原因有很多 :ref:`好处 <benefits_of_dependency_injection>`，你应该将其视为服务代码与其他所有内容之间的桥梁。这包括其他服务、外部 API，甚至是数据库。

.. _workers:

Worker
^^^^^^^

当入口点触发时，会创建一个 worker。worker 只是服务类的一个实例，但依赖声明会被替换为这些依赖的实例（参见 :ref:`依赖注入 <dependency_injection>` ）。

需要注意的是，worker 只在执行一个方法时存在——服务在每次调用之间是无状态的，这鼓励使用依赖项。

一个服务可以同时运行多个 worker，数量上限由用户定义。详细信息请参见 :ref:`并发 <concurrency>` 。

.. _dependency_injection:

依赖注入
--------------------

向服务类添加依赖项是声明式的。也就是说，类上的属性是一个声明，而不是 workers 实际可以使用的接口。

该类属性是一个 :class:`~nameko.extensions.DependencyProvider` 。它负责提供一个被注入到服务 worker 中的对象。

依赖提供者实现了一个 :meth:`~nameko.extensions.DependencyProvider.get_dependency` 方法，其结果被注入到新创建的 worker 中。

worker 的生命周期如下：

    #. 入口点触发
    #. 从服务类实例化 worker
    #. 依赖项注入到 worker 中
    #. 方法执行
    #. worker 被销毁

在伪代码中，这看起来像这样::

    worker = Service()
    worker.other_rpc = worker.other_rpc.get_dependency()
    worker.method()
    del worker

依赖提供者在服务的整个生命周期内存在，而注入的依赖项可以是每个 worker 唯一的。

.. _concurrency:

并发
-----------

Nameko 建立在 `eventlet <http://eventlet.net/>`_ 库之上，该库通过“绿色线程”提供并发。并发模型是带有隐式让渡的协程。

隐式让渡依赖于对标准库进行 `猴子补丁 <http://eventlet.net/doc/patching.html#monkeypatching-the-standard-library>`_，以在线程等待 I/O 时触发让渡。如果您通过命令行使用 ``nameko run`` 托管服务，Nameko 将为您应用猴子补丁。

每个 worker 在自己的绿色线程中执行。可以根据每个 worker 等待 I/O 的时间调整最大并发 worker 数量。

worker 是无状态的，因此本质上是线程安全的，但依赖项应确保它们在每个 worker 中是唯一的，或者可以安全地被多个 worker 并发访问。

请注意，许多使用套接字的 C 扩展，通常被认为是线程安全的，可能与绿色线程不兼容。其中包括 `librabbitmq <https://pypi.python.org/pypi/librabbitmq>`_ 、 `MySQLdb <http://mysql-python.sourceforge.net/MySQLdb.html>`_ 等。

.. _extensions:

扩展
----------

所有入口点和依赖提供者都被实现为“扩展”。我们这样称呼它们，因为它们在服务代码之外，但并不是所有服务都需要（例如，一个完全暴露于 AMQP 的服务不会使用 HTTP 入口点）。

Nameko 具有多种 :ref:`内置扩展 <built_in_extensions>` ，一些是 :ref:`由社区提供 <community_extensions>` ，您也可以 :ref:`自己编写 <writing_extensions>` 。

.. _running_services:

运行服务(Running Services)
------------------------------

运行服务所需的仅仅是服务类和任何相关的配置。运行一个或多个服务的最简单方法是使用 Nameko CLI::

    $ nameko run module:[ServiceClass]

此命令将发现给定 ``module``\s 中的 Nameko 服务并开始运行它们。您可以选择将其限制为特定的 ``ServiceClass``\s 。

.. _containers:

服务容器(Service Containers)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

每个服务类都委托给 :class:`~nameko.containers.ServiceContainer`。容器封装了运行服务所需的所有功能，并且还封装了服务类上的任何 :ref:`扩展 <extensions>`。

使用 ``ServiceContainer`` 运行单个服务：

.. literalinclude:: examples/service_container.py

.. _runner:

服务运行器(Service Runner)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:class:`~nameko.runners.ServiceRunner` 是对多个容器的一个薄包装，暴露出同时启动和停止所有包装容器的方法。这就是 ``nameko run`` 在内部使用的方式，它也可以通过编程构造：

.. literalinclude:: examples/service_runner.py

如果您创建自己的运行器而不是使用 `nameko run` ，您还必须应用 eventlet 的 `monkey patch <http://eventlet.net/doc/patching.html#monkeypatching-the-standard-library>`_ 。

有关示例，请参见 `nameko.cli.run <https://github.com/nameko/nameko/blob/cc13802d8afb059419384e2e2016bae7fe1415ce/nameko/cli/run.py#L3-L4>`_ 模块。

