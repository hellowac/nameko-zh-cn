贡献
============

Nameko 在 `GitHub <https://github.com/nameko/nameko>`_ 上开发，欢迎贡献。

请使用 GitHub 的 `issues <https://github.com/nameko/nameko/issues>`_ 来报告错误和提出功能请求。

欢迎你 `fork <https://github.com/nameko/nameko/fork>`_ 仓库并提交包含你贡献的拉取请求。

你可以使用以下命令安装所有开发依赖项::

    pip install -e .[dev]

以及构建文档所需的依赖项::

    pip install -e .[docs]

拉取请求将通过 `Travis-CI <https://travis-ci.org/nameko/nameko/>`_ 自动构建。除非以下所有条件都为真，否则 Travis 将会失败：

* 所有测试通过
* 测试的行覆盖率达到 100%
* 文档成功构建（包括拼写检查）

有关贡献的更多指导，请参见 :ref:`联系方式 <getting_in_touch>` 。

运行测试
--------------------

有一个 Makefile，提供了运行测试的便捷命令。要在本地运行测试，你必须安装并运行 RabbitMQ :ref:`installed <installation>` ，然后调用::

    $ make test