from __future__ import absolute_import

import itertools
import time
from logging import getLogger

from eventlet import Timeout
from eventlet.event import Event

from nameko.extensions import Entrypoint


_log = getLogger(__name__)


class Timer(Entrypoint):
    def __init__(self, interval, eager=False, **kwargs):
        """
        定时器入口点。每隔 `interval` 秒触发一次，或在上一个工作线程完成后立即触发（如果上一个工作线程耗时更长）。

        默认行为是在第一次触发之前等待 `interval` 秒。
        如果希望入口点在服务启动时立即触发，请传递 `eager=True`。

        示例::

            timer = Timer.decorator

            class Service(object):
                name = "service"

                @timer(interval=5)
                def tick(self):
                    pass

        """
        self.interval = interval
        self.eager = eager
        self.should_stop = Event()
        self.worker_complete = Event()
        self.gt = None
        super(Timer, self).__init__(**kwargs)

    def start(self):
        _log.debug("启动 %s", self)
        self.gt = self.container.spawn_managed_thread(self._run)

    def stop(self):
        _log.debug("停止 %s", self)
        self.should_stop.send(True)
        self.gt.wait()

    def kill(self):
        _log.debug("终止 %s", self)
        self.gt.kill()

    def _run(self):
        """运行间隔循环。"""

        def get_next_interval():
            start_time = time.time()
            start = 0 if self.eager else 1
            for count in itertools.count(start=start):
                yield max(start_time + count * self.interval - time.time(), 0)

        interval = get_next_interval()
        sleep_time = next(interval)
        while True:
            # 睡眠 `sleep_time`，除非 `should_stop` 被触发，此时我们将离开 while 循环并完全停止
            with Timeout(sleep_time, exception=False):
                self.should_stop.wait()
                break

            self.handle_timer_tick()

            self.worker_complete.wait()
            self.worker_complete.reset()

            sleep_time = next(interval)

    def handle_timer_tick(self):
        args = ()
        kwargs = {}

        # 注意，我们在这里不捕获 ContainerBeingKilled。如果抛出该异常，
        # 我们无能为力。异常会冒泡，并由 :meth:`Container._handle_thread_exited` 捕获，
        # 尽管触发的 `kill` 是无操作的，因为容器已经处于 `_being_killed` 状态。
        self.container.spawn_worker(
            self, args, kwargs, handle_result=self.handle_result
        )

    def handle_result(self, worker_ctx, result, exc_info):
        self.worker_complete.send()
        return result, exc_info


timer = Timer.decorator
