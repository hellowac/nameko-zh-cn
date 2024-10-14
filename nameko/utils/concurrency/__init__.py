import sys

import eventlet
from eventlet.queue import LightQueue


def fail_fast_imap(pool, call, items):
    """对给定列表中的每个项运行一个函数，逐个生成每个函数结果，其中函数调用在由提供的池生成的 :class:`~eventlet.greenthread.GreenThread` 中处理。

    如果任何函数引发异常，则所有其他正在进行的线程将被终止，并将异常抛给调用者。

    此函数类似于 :meth:`~eventlet.greenpool.GreenPool.imap`。

    :param pool: 用于生成函数线程的池  
    :type pool: eventlet.greenpool.GreenPool  
    :param call: 要调用的函数，期望从给定列表中接收一个项  
    """
    result_queue = LightQueue(maxsize=len(items))
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
            # Kill all other ongoing threads
            for ongoing_thread in spawned_threads:
                ongoing_thread.kill()
            # simply raising here (even raising a full exc_info) isn't
            # sufficient to preserve the original stack trace.
            # greenlet.throw() achieves this.
            eventlet.getcurrent().throw(*exc_info)
        yield result


class SpawningProxy(object):
    def __init__(self, items, abort_on_error=False):
        """ 
        
        将一组可迭代项封装，使得对返回的 `SpawningProxy` 实例的调用将在每个项上生成一个 :class:`~eventlet.greenthread.GreenThread` 。

        当每个生成的线程完成时返回。

        :param items: 要处理的可迭代项集  
        :param abort_on_error: 如果为 True, 任何在单个项调用中引发的异常将导致所有同级项调用线程被终止，并立即将异常传播给调用者。
        """
        self._items = items
        self.abort_on_error = abort_on_error

    def __getattr__(self, name):

        def spawning_method(*args, **kwargs):
            items = self._items
            if items:
                pool = eventlet.GreenPool(len(items))

                def call(item):
                    return getattr(item, name)(*args, **kwargs)

                if self.abort_on_error:
                    return list(fail_fast_imap(pool, call, self._items))
                else:
                    return list(pool.imap(call, self._items))
        return spawning_method


class SpawningSet(set):
    """ 一个具有 ``.all`` 属性的集合，该属性将在集合中的每个项上生成一个方法调用，每个调用都会在其自己的（并行）绿色线程中执行。
    """
    @property
    def all(self):
        return SpawningProxy(self)
