命令行界面
======================

Nameko 提供了一个命令行界面，使托管和与服务交互变得尽可能简单。

.. _running_a_service:

运行服务
-----------------

.. code-block:: shell

    $ nameko run <module>[:<ServiceClass>]

发现并运行一个服务类。此命令将在前台启动服务，并运行直到进程终止。

可以使用 ``--config`` 选项覆盖默认设置

.. code-block:: shell

    $ nameko run --config ./foobar.yaml <module>[:<ServiceClass>]


并提供一个简单的 YAML 配置文件：

.. code-block:: yaml

    # foobar.yaml

    AMQP_URI: 'pyamqp://guest:guest@localhost'
    WEB_SERVER_ADDRESS: '0.0.0.0:8000'
    rpc_exchange: 'nameko-rpc'
    max_workers: 10
    parent_calls_tracked: 10

    LOGGING:
        version: 1
        handlers:
            console:
                class: logging.StreamHandler
        root:
            level: DEBUG
            handlers: [console]


``LOGGING`` 条目将传递给 :func:`logging.config.dictConfig`，并应符合该调用的模式。

配置值可以通过内置的 :ref:`config_dependency_provider` 依赖提供者读取。


环境变量替换
---------------------------------

YAML 配置文件支持环境变量。您可以使用 bash 风格的语法： ``${ENV_VAR}`` 。可选地，您可以提供默认值 ``${ENV_VAR:default_value}`` 。默认值可以递归包含环境变量 ``${ENV_VAR:default_${OTHER_ENV_VAR:value}}`` （注意：此功能需要 regex 包）。

.. code-block:: yaml

    # foobar.yaml
    AMQP_URI: pyamqp://${RABBITMQ_USER:guest}:${RABBITMQ_PASSWORD:password}@${RABBITMQ_HOST:localhost}

要运行您的服务并为其设置环境变量：

.. code-block:: shell

    $ RABBITMQ_USER=user RABBITMQ_PASSWORD=password RABBITMQ_HOST=host nameko run --config ./foobar.yaml <module>[:<ServiceClass>]

如果您需要在 YAML 文件中引用值，则需要显式使用 ``!env_var`` 解析器：

.. code-block:: yaml

    # foobar.yaml
    AMQP_URI: !env_var "pyamqp://${RABBITMQ_USER:guest}:${RABBITMQ_PASSWORD:password}@${RABBITMQ_HOST:localhost}"

如果您需要在 YAML 文件中将值用作原始字符串，而不希望它们转换为原生 Python 类型，则需要显式使用 ``!raw_env_var`` 解析器：

.. code-block:: yaml

    # foobar.yaml
    ENV_THAT_IS_NEEDED_RAW: !raw_env_var "${ENV_THAT_IS_NEEDED_RAW:1234.5660}"

这将变成字符串值 ``1234.5660``，而不是浮点数。

您可以提供多个级别的默认值：

.. code-block:: yaml

    # foobar.yaml
    AMQP_URI: ${AMQP_URI:pyamqp://${RABBITMQ_USER:guest}:${RABBITMQ_PASSWORD:password}@${RABBITMQ_HOST:localhost}}

此配置接受 AMQP_URI 作为环境变量，如果提供了，RABBITMQ_* 嵌套变量将不会被使用。

环境变量值被解释为 YAML，因此可以使用丰富的类型：

.. code-block:: yaml

    # foobar.yaml
    ...
    THINGS: ${A_LIST_OF_THINGS}

.. code-block:: shell

    $ A_LIST_OF_THINGS=[A,B,C] nameko run --config ./foobar.yaml <module>[:<ServiceClass>]

环境变量的解析器将配对所有括号。

.. code-block:: yaml

    # foobar.yaml
    LANDING_URL_TEMPLATE: ${LANDING_URL_TEMPLATE:https://example.com/{path}}

因此，此配置的默认值将是 `https://example.com/{path}` 。


与运行中的服务交互
---------------------------------

.. code-block:: pycon

    $ nameko shell

启动一个交互式 Python Shell，用于与远程 Nameko 服务进行交互。这是一个常规的交互式解释器，内置命名空间中增加了一个特殊模块 ``n``，提供了进行 RPC 调用和调度事件的能力。

向 "target_service" 进行 RPC 调用：

.. code-block:: pycon

    $ nameko shell
    >>> n.rpc.target_service.target_method(...)
    # RPC 响应


作为 "source_service" 调度事件：

.. code-block:: pycon

    $ nameko shell
    >>> n.dispatch_event("source_service", "event_type", "event_payload")

