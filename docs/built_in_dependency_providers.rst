.. _built_in_dependency_providers:

内置的依赖提供者
=============================

Nameko 包含一些常用的 :ref:`依赖提供者 <dependency_injection>`。本节将介绍它们并提供简要的使用示例。

.. _config_dependency_provider:

Config
------

配置(Config)是一个简单的依赖提供者，允许服务在运行时以只读方式访问配置值，见 :ref:`running_a_service` 。

.. literalinclude:: examples/config_dependency_provider.py