from __future__ import print_function

import argparse
import os
import re
from functools import partial

import yaml
from pkg_resources import get_distribution

from nameko.exceptions import CommandError, ConfigurationError

from . import commands


try:
    import regex
except ImportError:  # pragma: no cover
    has_regex_module = False
    ENV_VAR_MATCHER = re.compile(
        r"""
            \$\{       # 字符 `${` 的字面匹配
            ([^}:\s]+) # 第一个分组：匹配除 `}` 或 `:` 外的任何字符
            :?         # 零次或一次匹配字面量 `:` 字符
            ([^}]+)?   # 第二个分组：匹配除 `}` 外的任何字符
            \}         # 字符 `}` 的字面匹配
        """,
        re.VERBOSE,
    )
else:  # pragma: no cover
    has_regex_module = True
    ENV_VAR_MATCHER = regex.compile(
        r"""
        \$\{                # 匹配 ${
        (                   # 第一个捕获组：变量名
            [^{}:\s]+       # 变量名，不包含 {,},: 或空格
        )
        (?:                 # 非捕获的可选组，用于值
            :               # 匹配 :
            (               # 第二个捕获组：默认值
                (?:         # 非捕获组，表示 OR
                    [^{}]   # 任何非括号字符
                |           # 或
                    \{      # 字面量 {
                    (?2)    # 递归的第二个捕获组，即 ([^{}]|{(?2)})
                    \}      # 字面量 }
                )*          #
            )
        )?
        \}                  # 匹配结束 }
        """,
        regex.VERBOSE,
    )

    ### 代码功能说明：
    # - **模块导入**：尝试导入 `regex` 模块，如果导入失败，则使用标准库中的 `re` 模块。
    # - **正则表达式匹配**：定义了一个名为 `ENV_VAR_MATCHER` 的正则表达式，用于匹配环境变量的格式，支持可选的默认值。


IMPLICIT_ENV_VAR_MATCHER = re.compile(
    r"""
        .*          # 匹配任意数量的任意字符
        \$\{.*\}    # 匹配 `${` 和 `}` 之间的任意数量的任意字符，字面匹配
        .*          # 匹配任意数量的任意字符
    """,
    re.VERBOSE,
)

RECURSIVE_ENV_VAR_MATCHER = re.compile(
    r"""
        \$\{       # 字面匹配字符 `${`
        ([^}]+)?   # 匹配除 `}` 外的任何字符
        \}         # 字面匹配字符 `}`
        ([^$}]+)?  # 匹配除 `}` 或 `$` 外的任何字符
        \}         # 字面匹配字符 `}`
    """,
    re.VERBOSE,
)


# ### 代码功能说明：
# - **IMPLICIT_ENV_VAR_MATCHER**：定义了一个正则表达式，用于匹配环境变量格式的字符串，包括 `${...}`，在这个模式中，`${` 和 `}` 之间可以包含任意数量的字符。
# - **RECURSIVE_ENV_VAR_MATCHER**：定义了一个正则表达式，用于匹配嵌套的环境变量格式。它可以匹配形式如 `${...}`，并且支持在 `${...}` 结构内存在额外的 `${...}` 结构。


def setup_parser():
    """启动时，设置 argparser 以及定义的命令行"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", "--version", action="version", version=get_distribution("nameko").version
    )
    subparsers = parser.add_subparsers()

    # 将commands中定义的命令添加到命令解析行
    for command in commands.commands:
        command_parser = subparsers.add_parser(
            command.name,
            description=command.__doc__,
        )
        command.init_parser(command_parser)
        command_parser.set_defaults(main=command.main)
    return parser


def _replace_env_var(match: regex.Match):
    env_var, default = match.groups()
    value = os.environ.get(env_var, None)
    if value is None:
        # 使用其他变量扩展默认值
        if default is None:
            # 如果引擎没有进入默认捕获组，regex模块返回None而不是空字符串
            default = ""

        value = default
        while IMPLICIT_ENV_VAR_MATCHER.match(value):  # pragma: no cover
            value = ENV_VAR_MATCHER.sub(_replace_env_var, value)  # type: ignore
    return value


def env_var_constructor(loader: yaml.SafeLoader, node: yaml.Node, raw: bool = False):
    if not isinstance(node, yaml.ScalarNode):
        raise ValueError("类型错误")

    raw_value = loader.construct_scalar(node)

    # 检测并对递归环境变量报错
    if not has_regex_module and RECURSIVE_ENV_VAR_MATCHER.match(
        raw_value
    ):  # pragma: no cover
        raise ConfigurationError("嵌套的环境变量查找需要使用 `regex` 模块。")
    value = ENV_VAR_MATCHER.sub(_replace_env_var, raw_value)  # type: ignore
    if value == raw_value:
        return value  # avoid recursion
    return value if raw else yaml.safe_load(value)


def setup_yaml_parser():
    yaml.add_constructor("!env_var", env_var_constructor, yaml.SafeLoader)
    yaml.add_constructor(
        "!raw_env_var", partial(env_var_constructor, raw=True), yaml.SafeLoader
    )
    yaml.add_implicit_resolver(
        "!env_var", IMPLICIT_ENV_VAR_MATCHER, Loader=yaml.SafeLoader
    )


def main():
    parser = setup_parser()
    args, unknown_args = parser.parse_known_args()
    print(f"{args = }")
    setup_yaml_parser()
    try:
        args.main(args, *unknown_args)
    except (CommandError, ConfigurationError) as exc:
        print("Error: {}".format(exc))
