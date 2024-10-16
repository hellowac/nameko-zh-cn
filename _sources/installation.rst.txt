.. _installation:

安装
============

通过 Pip 安装
----------------

您可以使用 pip 从 `PyPI <https://pypi.python.org/pypi/nameko>`_ 安装 nameko 及其依赖项::

    pip install nameko


源代码
-----------

Nameko 在 `GitHub <https://github.com/nameko/nameko>`_ 上积极开发。通过克隆公共仓库获取代码::

    git clone git@github.com:nameko/nameko.git

您可以使用 setuptools 从源代码安装::

    python setup.py install


RabbitMQ
--------

Nameko 的多个内置功能依赖于 RabbitMQ。在大多数平台上安装 RabbitMQ 都很简单，并且它们提供了 `出色的文档 <https://www.rabbitmq.com/download.html>`_ 。

在 mac 上使用 homebrew 可以通过以下命令安装::

    brew install rabbitmq

在基于 Debian 的操作系统上::

    apt-get install rabbitmq-server

对于其他平台，请参考 `RabbitMQ 安装指南 <https://www.rabbitmq.com/download.html>`_ 。

RabbitMQ 代理安装后即可使用——不需要任何配置。本文档中的示例假设您在本地主机的默认端口上运行代理，并且已启用 `rabbitmq_management <http://www.rabbitmq.com/management.html>`_ 插件。