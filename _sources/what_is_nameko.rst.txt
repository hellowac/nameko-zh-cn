什么是 Nameko?
===============

Nameko 是一个用于构建 Python 微服务的框架。

它内置支持以下功能：

* 基于 AMQP 的 RPC
* 基于 AMQP 的异步事件（发布-订阅模式）
* 简单的 HTTP GET 和 POST 请求
* Websocket RPC 和订阅（实验性功能）

开箱即用，你可以构建一个服务，响应 RPC 消息、在某些操作时分发事件、并监听来自其他服务的事件。它还可以为无法使用 AMQP 的客户端提供 HTTP 接口，并为如 JavaScript 客户端提供 websocket 接口。

Nameko 也具有可扩展性。你可以定义自己的传输机制和服务依赖，按需混合搭配。

Nameko 强烈支持 :ref:`依赖注入 <benefits_of_dependency_injection>` 模式，使服务的构建和测试变得简单明了。

Nameko 的名字源自日本的一种蘑菇，这种蘑菇通常成簇生长。

何时使用 Nameko？
------------------

Nameko 旨在帮助你创建、运行和测试微服务。你应该在以下情况下使用 Nameko：

* 你想将后端编写为微服务，或
* 你想在现有系统中添加微服务，并且
* 你希望使用 Python 实现这些功能。

Nameko 可以从单个服务实例扩展到拥有多个不同服务实例的集群。

该库还附带了客户端工具，允许你编写 Python 代码来与现有的 Nameko 集群通信。

何时不应该使用 Nameko？
------------------------

Nameko 不是一个 Web 框架。虽然它内置了 HTTP 支持，但仅限于微服务领域中的实用功能。如果你想构建一个供人类使用的 Web 应用程序，建议使用类似 `Flask <http://flask.pocoo.org>`_ 这样的框架。