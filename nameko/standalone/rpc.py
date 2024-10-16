from __future__ import absolute_import, annotations

import logging
import socket
from typing import Dict

from amqp.exceptions import ConnectionError
from kombu import Connection
from kombu.common import maybe_declare
from kombu.messaging import Consumer

from nameko import serialization
from nameko.constants import (
    AMQP_SSL_CONFIG_KEY,
    AMQP_URI_CONFIG_KEY,
    LOGIN_METHOD_CONFIG_KEY,
)
from nameko.containers import WorkerContext
from nameko.exceptions import RpcTimeout
from nameko.extensions import Entrypoint
from nameko.rpc import ReplyListener, ServiceProxy


_logger = logging.getLogger(__name__)


class ConsumeEvent(object):
    """具有与 eventlet.Event 相同接口的 RPC 消费者的事件。"""

    exception = None

    def __init__(self, queue_consumer: PollingQueueConsumer, correlation_id: str):
        self.correlation_id = correlation_id
        self.queue_consumer = queue_consumer

    def send(self, body):
        self.body = body

    def send_exception(self, exc):
        self.exception = exc

    def wait(self):
        """对其 `queue_consumer` 进行阻塞调用，直到处理完具有给定 `correlation_id` 的消息。

        在阻塞调用退出时， `self.send()` 将被调用，并传入接收到的消息的主体（参见 :meth:`~nameko.rpc.ReplyListener.handle_message` ）。

        异常将被直接引发。
        """
        # 在开始等待之前已断开连接。
        if self.exception:
            raise self.exception

        if self.queue_consumer.stopped:
            raise RuntimeError(
                "This consumer has been stopped, and can no longer be used"
            )
        if self.queue_consumer.connection.connected is False:
            # 我们不能在这里直接重连。
            # 消费者（及其独占的、自动删除的回复队列）必须在发送任何请求之前重新建立，
            # 否则在响应发布时回复队列可能不存在。
            raise RuntimeError(
                "This consumer has been disconnected, and can no longer " "be used"
            )

        try:
            self.queue_consumer.get_message(self.correlation_id)
        except socket.error as exc:
            self.exception = exc

        # disconnected while waiting
        if self.exception:
            raise self.exception
        return self.body


class PollingQueueConsumer(object):
    """实现了 :class:`~messaging.QueueConsumer` 的最小接口。
    它不是在单独的线程中处理消息，而是提供了一种轮询方法，以阻塞直到到达具有相同关联 ID 的 RPC 代理调用的消息。
    """

    consumer = None

    def __init__(self, timeout=None):
        self.stopped = True
        self.timeout = timeout
        self.replies = {}

    def _setup_consumer(self):
        if self.consumer is not None:
            try:
                self.consumer.cancel()
            except (socket.error, IOError):  # pragma: no cover
                # 在某些系统上（例如 macOS），我们需要在这里显式地取消消费者。
                # 然而，例如在 Ubuntu 14.04 上，断开连接已经关闭了套接字。
                # 我们尝试取消，并忽略任何套接字错误。
                # 如果套接字已关闭，则会引发 IOError，忽略它并假设消费者已经被取消。
                pass

        channel = self.connection.channel()
        # queue.bind returns a bound copy
        self.queue = self.queue.bind(channel)
        maybe_declare(self.queue, channel)
        consumer = Consumer(
            channel, queues=[self.queue], accept=self.accept, no_ack=False
        )
        consumer.callbacks = [self.on_message]
        consumer.consume()
        self.consumer = consumer

    def register_provider(self, provider):
        self.provider = provider

        self.serializer, self.accept = serialization.setup(provider.container.config)

        amqp_uri = provider.container.config[AMQP_URI_CONFIG_KEY]
        ssl = provider.container.config.get(AMQP_SSL_CONFIG_KEY)
        login_method = provider.container.config.get(LOGIN_METHOD_CONFIG_KEY)
        self.connection = Connection(amqp_uri, ssl=ssl, login_method=login_method)

        self.queue = provider.queue
        self._setup_consumer()
        self.stopped = False

    def unregister_provider(self, provider):
        self.connection.close()
        self.stopped = True

    def ack_message(self, msg):
        msg.ack()

    def on_message(self, body, message):
        msg_correlation_id = message.properties.get("correlation_id")
        if msg_correlation_id not in self.provider._reply_events:
            _logger.debug("Unknown correlation id: %s", msg_correlation_id)

        self.replies[msg_correlation_id] = (body, message)

    def get_message(self, correlation_id):
        try:
            while correlation_id not in self.replies:
                self.consumer.connection.drain_events(timeout=self.timeout)

            body, message = self.replies.pop(correlation_id)
            self.provider.handle_message(body, message)

        except socket.timeout:
            # TODO: 这将RPC超时与套接字读取超时混淆。如果RPC超时尚未达到，更好的RPC代理实现应该能够从套接字超时中恢复。
            timeout_error = RpcTimeout(self.timeout)
            event = self.provider._reply_events.pop(correlation_id)
            event.send_exception(timeout_error)

            # 超时是通过套接字超时实现的，因此当超时发生时，连接会被关闭并必须重新建立。
            self._setup_consumer()

        except (IOError, ConnectionError):
            # 如果这是一个临时错误，尝试重新连接并重试。如果我们无法重新连接，错误将被抛出。
            self._setup_consumer()
            self.get_message(correlation_id)

        except KeyboardInterrupt as exc:
            event = self.provider._reply_events.pop(correlation_id)
            event.send_exception(exc)
            # exception may have killed the connection
            self._setup_consumer()


class SingleThreadedReplyListener(ReplyListener):
    """一个使用自定义队列消费者和 `ConsumeEvent` 的 `ReplyListener` 。"""

    queue_consumer = None

    def __init__(self, timeout=None):
        self.queue_consumer = PollingQueueConsumer(timeout=timeout)
        super(SingleThreadedReplyListener, self).__init__()
        self._reply_events: Dict[str, ConsumeEvent] = {}

    def get_reply_event(self, correlation_id: str):
        # 应该永远不会抛出此异常
        if self.queue_consumer is None:
            raise Exception("队列消费者为空")

        reply_event = ConsumeEvent(self.queue_consumer, correlation_id)
        self._reply_events[correlation_id] = reply_event
        return reply_event


class StandaloneProxyBase(object):
    class ServiceContainer(object):
        """实现了 :class:`~containers.ServiceContainer` 的最小接口，以供该模块中的子类和 RPC 导入使用。"""

        service_name = "standalone_rpc_proxy"

        def __init__(self, config):
            self.config = config
            self.shared_extensions = {}

    class Dummy(Entrypoint):
        method_name = "call"

    _proxy = None

    def __init__(
        self,
        config: dict,
        context_data=None,
        timeout=None,
        reply_listener_cls=SingleThreadedReplyListener,
    ):
        container = self.ServiceContainer(config)

        self._worker_ctx = WorkerContext(
            container, service=None, entrypoint=self.Dummy, data=context_data
        )
        self._reply_listener = reply_listener_cls(timeout=timeout).bind(container)

    def __enter__(self):
        return self.start()

    def __exit__(self, tpe, value, traceback):
        self.stop()

    def start(self):
        self._reply_listener.setup()
        return self._proxy

    def stop(self):
        self._reply_listener.stop()


class ServiceRpcProxy(StandaloneProxyBase):
    """
    一个单线程的 RPC 代理，用于命名服务。代理上的方法调用会转换为对服务的 RPC 调用，并直接返回响应。

    允许未托管在 Nameko 中的服务向 Nameko 集群发出 RPC 请求。通常用作上下文管理器，但也可以手动启动和停止。

    *用法*

    作为上下文管理器使用::

        with ServiceRpcProxy('targetservice', config) as proxy:
            proxy.method()

    等效的调用，手动启动和停止::

        targetservice_proxy = ServiceRpcProxy('targetservice', config)
        proxy = targetservice_proxy.start()
        proxy.method()
        targetservice_proxy.stop()

    如果调用了 ``start()`` ，则必须最终调用 ``stop()`` 以关闭与代理的连接。

    您还可以提供 ``context_data`` ，这是一个数据字典，将被序列化到 AMQP 消息头中，并指定自定义的工作上下文类以序列化它们。
    """

    def __init__(self, service_name, *args, **kwargs):
        super(ServiceRpcProxy, self).__init__(*args, **kwargs)
        self._proxy = ServiceProxy(self._worker_ctx, service_name, self._reply_listener)


class ClusterProxy(object):
    """
    一个单线程的 RPC 代理，用于服务集群。可以通过属性访问各个服务，这些属性返回服务代理。代理上的方法调用会转换为对服务的 RPC 调用，并直接返回响应。

    允许未托管在 Nameko 中的服务向 Nameko 集群发出 RPC 请求。通常用作上下文管理器，但也可以手动启动和停止。

    这类似于服务代理，但可以为所有服务的调用使用一个单独的回复队列，而一组服务代理则会为每个代理拥有一个回复队列。

    *用法*

    作为上下文管理器使用::

        with ClusterRpcProxy(config) as proxy:
            proxy.service.method()
            proxy.other_service.method()

    等效的调用，手动启动和停止::

        proxy = ClusterRpcProxy(config)
        proxy = proxy.start()
        proxy.targetservice.method()
        proxy.other_service.method()
        proxy.stop()

    如果调用了 ``start()`` ，则必须最终调用 ``stop()`` 以关闭与代理的连接。

    您还可以提供 ``context_data`` ，这是一个数据字典，将被序列化到 AMQP 消息头中，并指定自定义的工作上下文类以序列化它们。

    当服务名称在 Python 中不合法时，您也可以使用类似字典的语法::

        with ClusterRpcProxy(config) as proxy:
            proxy['service-name'].method()
            proxy['other-service'].method()
    """

    def __init__(self, worker_ctx, reply_listener):
        self._worker_ctx = worker_ctx
        self._reply_listener = reply_listener

        self._proxies = {}

    def __getattr__(self, name):
        if name not in self._proxies:
            self._proxies[name] = ServiceProxy(
                self._worker_ctx, name, self._reply_listener
            )
        return self._proxies[name]

    def __getitem__(self, name):
        """Enable dict-like access on the proxy."""
        return getattr(self, name)


class ClusterRpcProxy(StandaloneProxyBase):
    def __init__(self, *args, **kwargs):
        super(ClusterRpcProxy, self).__init__(*args, **kwargs)
        self._proxy = ClusterProxy(self._worker_ctx, self._reply_listener)
