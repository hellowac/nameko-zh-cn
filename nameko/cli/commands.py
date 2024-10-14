"""命令在此处定义，并且导入语句内联，以避免触发其他子命令的导入
（例如，`run` 将导致 eventlet 的猴子补丁，而我们不希望在 `shell` 中发生这种情况）。

"""
from .actions import FlagAction


class Command(object):
    name = None

    @staticmethod
    def init_parser(parser):
        raise NotImplementedError  # pragma: no cover

    @staticmethod
    def main(args, *unknown_args):
        # 使用内联导入以避免触发其他子命令的导入。
        raise NotImplementedError  # pragma: no cover


class Backdoor(Command):
    """连接到 Nameko 后门。

    如果后门正在运行，这将连接到远程 shell。运行器通常可用作 `runner` 。
    """

    name = 'backdoor'

    @staticmethod
    def init_parser(parser):
        parser.add_argument(
            'target', metavar='[host:]port',
            help="(host and) port to connect to",
        )
        parser.add_argument(
            '--rlwrap', dest='rlwrap', action=FlagAction,
            help='Use rlwrap')
        parser.set_defaults(feature=True)
        return parser

    @staticmethod
    def main(args, *unknown_args):
        from .backdoor import main
        main(args)


class ShowConfig(Command):
    """以 YAML 字符串的形式输出将传递给服务的配置。

    这对于查看从环境变量加载值的配置文件非常有用。
    """

    name = 'show-config'

    @staticmethod
    def init_parser(parser):

        parser.add_argument(
            '--config', default='config.yaml',
            help='The YAML configuration file')

        return parser

    @staticmethod
    def main(args, *unknown_args):
        from .show_config import main
        main(args)


class Run(Command):
    """运行 Nameko 服务。给定一个 Python 模块的路径，该模块包含一个或多个 Nameko 服务，将会托管并运行它们。
    
    默认情况下，这将尝试找到看起来像服务的类（任何具有 Nameko 入口点的内容），但可以通过 ``nameko run module:ServiceClass`` 指定特定的服务。
    """

    name = 'run'

    @staticmethod
    def init_parser(parser):
        parser.add_argument(
            'services', nargs='+',
            metavar='module[:service class]',
            help='python path to one or more service classes to run')

        parser.add_argument(
            '--config', default='',
            help='The YAML configuration file')

        parser.add_argument(
            '--broker', default='pyamqp://guest:guest@localhost',
            help='RabbitMQ broker url')

        parser.add_argument(
            '--backdoor-port', type=int,
            help='Specify a port number to host a backdoor, which can be'
            ' connected to for an interactive interpreter within the running'
            ' service process using `nameko backdoor`.')

        return parser

    @staticmethod
    def main(args, *unknown_args):
        import eventlet
        eventlet.monkey_patch()  # noqa (code before imports)

        from .run import main
        main(args)


class Shell(Command):
    """启动一个交互式 Python shell, 以便与远程 Nameko 服务进行交互。

    这是一个常规的交互式解释器，内置命名空间中添加了一个特殊模块 ``n``，提供 ``n.rpc`` 和 ``n.dispatch_event``。
    """

    name = 'shell'

    SHELLS = ['bpython', 'ipython', 'plain']

    @classmethod
    def init_parser(cls, parser):
        parser.add_argument(
            '--broker', default='pyamqp://guest:guest@localhost',
            help='RabbitMQ broker url')
        parser.add_argument(
            '--interface', choices=cls.SHELLS,
            help='Specify an interactive interpreter interface.'
                 ' (Ignored if not in TTY mode)')
        parser.add_argument(
            '--config', default='',
            help='The YAML configuration file')
        return parser

    @staticmethod
    def main(args, *unknown_args):
        from .shell import main
        main(args)


class Test(Command):
    name = "test"

    @staticmethod
    def init_parser(parser):
        return parser

    @staticmethod
    def main(args, *unknown_args):
        import eventlet
        eventlet.monkey_patch()  # noqa (code before imports)

        import sys

        import pytest

        args = list(unknown_args)
        args.extend(
            ["-W", "ignore:Module already imported:_pytest.warning_types.PytestWarning"]
        )

        exit_code = pytest.main(args)
        sys.exit(int(exit_code))


commands = Command.__subclasses__()  # pylint: disable=E1101
