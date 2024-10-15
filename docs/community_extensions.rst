.. _community_extensions:


社区
=========

有许多 Nameko 扩展和补充库并不是核心项目的一部分，但在开发自己的 Nameko 服务时，您可能会发现它们非常有用：

扩展
----------

* `nameko-sqlalchemy <https://github.com/onefinestay/nameko-sqlalchemy>`_

  用于使用 SQLAlchemy 写入数据库的 ``DependencyProvider`` 。需要一个纯 Python 或其他与 eventlet 兼容的数据库驱动程序。

  考虑将其与 `SQLAlchemy-filters <https://github.com/Overseas-Student-Living/sqlalchemy-filters>`_ 结合使用，以在通过 REST API 暴露查询对象时添加过滤、排序和分页功能。

* `nameko-sentry <https://github.com/mattbennett/nameko-sentry>`_

  捕获入口点异常并将追踪信息发送到 `Sentry <https://getsentry.com/>`_ 服务器。

* `nameko-amqp-retry <https://github.com/nameko/nameko-amqp-retry>`_

  允许 AMQP 入口点稍后重试的 Nameko 扩展。

* `nameko-bayeux-client <https://github.com/Overseas-Student-Living/nameko-bayeux-client>`_

  实现 Bayeux 协议的 Cometd 客户端的 Nameko 扩展。

* `nameko-slack <https://github.com/iky/nameko-slack>`_

  用于与 Slack API 交互的 Nameko 扩展。使用 Python 的 Slack 开发者工具包。

* `nameko-eventlog-dispatcher <https://github.com/sohonetlabs/nameko-eventlog-dispatcher>`_

  使用事件（发布-订阅）调度日志数据的 Nameko 依赖提供者。

* `nameko-redis-py <https://github.com/fraglab/nameko-redis-py>`_

  Nameko 的 Redis 依赖和工具。

* `nameko-redis <https://github.com/etataurov/nameko-redis/>`_

  Nameko 服务的 Redis 依赖。

* `nameko-statsd <https://github.com/sohonetlabs/nameko-statsd>`_

  Nameko 的 StatsD 依赖，使服务能够发送统计信息。

* `nameko-twilio <https://github.com/invictuscapital/nameko-twilio>`_

  Nameko 的 Twilio 依赖，使您可以在服务中发送 SMS、拨打电话和接听电话。

* `nameko-sendgrid <https://github.com/invictuscapital/nameko-sendgrid>`_

  Nameko 的 SendGrid 依赖，用于发送事务性和营销邮件。

* `nameko-cachetools <https://github.com/santiycr/nameko-cachetools>`_

  用于缓存 Nameko 服务之间 RPC 交互的工具。

补充库
-----------------------

* `django-nameko <https://github.com/and3rson/django-nameko>`_

  用于 Nameko 微服务框架的 Django 封装。

* `flask_nameko <https://github.com/clef/flask-nameko>`_

  用于在 Flask 中使用 Nameko 服务的封装。

* `nameko-proxy <https://github.com/fraglab/nameko-proxy>`_

  与 Nameko 微服务通信的独立异步代理。

在 PyPi 中搜索更多 `nameko 包 <https://pypi.python.org/pypi?%3Aaction=search&term=nameko&submit=search>`_

如果您希望自己的 Nameko 扩展或库出现在此页面上，请 :ref:`与我们联系 <getting_in_touch>` 。
