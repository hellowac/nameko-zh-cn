from __future__ import annotations

import sys

from typing import List, Type, Iterable, Iterator, Callable, Sized, Generator

import nameko.containers
import eventlet
from eventlet.queue import LightQueue


def fail_fast_imap(
    pool: eventlet.GreenPool, call: Callable[[Type]], items: Iterable[Type]
):
    """对给定列表中的每个项运行一个函数，逐个生成每个函数结果，其中函数调用在由提供的池生成的 :class:`~eventlet.greenthread.GreenThread` 中处理。

    如果任何函数引发异常，则所有其他正在进行的线程将被终止，并将异常抛给调用者。

    此函数类似于 :meth:`~eventlet.greenpool.GreenPool.imap`。

    :param pool: 用于生成函数线程的池
    :type pool: eventlet.greenpool.GreenPool
    :param call: 要调用的函数，期望从给定列表中接收一个项
    """
    result_queue = LightQueue(maxsize=len(items))  # type: ignore
    spawned_threads = set()

    def handle_result(finished_thread):
        try:
            thread_result = finished_thread.wait()
            spawned_threads.remove(finished_thread)
            result_queue.put((thread_result, None))
        except Exception:
            spawned_threads.remove(finished_thread)
            result_queue.put((None, sys.exc_info()))

    for item in items:
        gt = pool.spawn(call, item)
        spawned_threads.add(gt)
        gt.link(handle_result)

    while spawned_threads:
        result, exc_info = result_queue.get()
        if exc_info is not None:
            # 终止所有其他正在进行的线程。
            for ongoing_thread in spawned_threads:
                ongoing_thread.kill()
            # 仅在此处抛出异常（即使抛出完整的 exc_info）也不足以保留原始的堆栈跟踪。
            # 使用 `greenlet.throw()` 可以实现这一点。
            eventlet.getcurrent().throw(*exc_info)
        yield result


class SpawningProxy(object):
    def __init__(self, items: Iterable[nameko.containers.ServiceContainer], abort_on_error: bool = False):
        """并行代理类

        将一组可迭代项封装，使得对返回的 `SpawningProxy` 实例的调用将在每个项上生成一个 :class:`~eventlet.greenthread.GreenThread` 。

        当每个生成的线程完成时返回。

        :param items: 要处理的可迭代项集
        :param abort_on_error: 如果为 True, 任何在单个项调用中引发的异常将导致所有同级项调用线程被终止，并立即将异常传播给调用者。


        chatGPT回答:

        SpawningProxy 的主要功能是并行调用一组对象的方法。
        它使用 eventlet 提供的协程池来管理并发，并支持错误传播机制。
        如果有多个对象需要并行执行某个相同的操作，此类可以有效封装该逻辑。
        """
        self._items: Iterable[Type] = items
        self.abort_on_error: bool = abort_on_error

    def __getattr__(self, name: str):
        def spawning_method(*args, **kwargs) -> List[eventlet.greenthread.GreenThread]:
            """ 
            
            该方法接收任意参数 (*args, **kwargs)，这些参数将传递给 items 中每个对象的对应方法(name 指定)。
            """
            items = self._items

            if items:

                # 创建一个协程池，池的大小等于 items 的数量。
                pool = eventlet.GreenPool(len(items))  # type: ignore

                def call(item: Type):
                    """内部定义了一个小函数 call, 它用于在每个 item 对象上调用对应的方法 name, 并传入之前的参数。"""
                    return getattr(item, name)(*args, **kwargs)

                if self.abort_on_error:
                    # 如果其中一个对象的调用过程中发生异常，所有并行线程会立即终止，异常会传播。
                    return list(fail_fast_imap(pool, call, self._items))
                
                else:
                    # 通过 GreenPool 对 items 集合进行并行处理。
                    return list(pool.imap(call, self._items)) 

            # 应该永远不会走到这，除非在服务（Service）为 0 的情况下启动该命令
            return []

        return spawning_method


class SpawningSet(set):
    """一个具有 ``.all`` 属性的集合，该属性将在集合中的每个项上生成一个方法调用，每个调用都会在其自己的（并行）绿色线程中执行。"""

    @property
    def all(self):
        return SpawningProxy(self)
