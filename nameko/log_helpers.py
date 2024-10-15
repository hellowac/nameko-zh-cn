from __future__ import absolute_import

import logging
import time
from contextlib import contextmanager


def make_timing_logger(logger, precision=3, level=logging.DEBUG):
    """返回一个计时记录器。

    用法::

        >>> logger = logging.getLogger('foobar')
        >>> log_time = make_timing_logger(
        ...     logger, level=logging.INFO, precision=2)
        >>>
        >>> with log_time("hello %s", "world"):
        ...     time.sleep(1)
        INFO:foobar:hello world in 1.00s
    """

    @contextmanager
    def log_time(msg, *args):
        """在上下文块退出时，记录 `msg` 和 `*args` 以及（简单的挂钟）计时信息。"""
        start_time = time.time()

        try:
            yield
        finally:
            message = "{} in %0.{}fs".format(msg, precision)
            duration = time.time() - start_time
            args = args + (duration,)
            logger.log(level, message, *args)

    return log_time
