"""
提供核心消息装饰器和依赖项提供者。
"""

from __future__ import absolute_import

import warnings
from functools import partial
from logging import getLogger

import six
from amqp.exceptions import ConnectionError
from eventlet.event import Event
from kombu import Connection
from kombu.common import maybe_declare
from kombu.mixins import ConsumerMixin

from nameko.amqp.publish import Publisher as PublisherCore
from nameko.amqp.publish import get_connection
from nameko.constants import (
    AMQP_SSL_CONFIG_KEY,
    AMQP_URI_CONFIG_KEY,
    DEFAULT_HEARTBEAT,
    DEFAULT_TRANSPORT_OPTIONS,
    HEADER_PREFIX,
    HEARTBEAT_CONFIG_KEY,
    LOGIN_METHOD_CONFIG_KEY,
    TRANSPORT_OPTIONS_CONFIG_KEY,
)
from nameko.exceptions import ContainerBeingKilled
from nameko.extensions import (
    DependencyProvider,
    Entrypoint,
    ProviderCollector,
    SharedExtension,
)
from nameko.utils import sanitize_url


_log = getLogger(__name__)


class HeaderEncoder(object):
    header_prefix = HEADER_PREFIX

    def _get_header_name(self, key):
        return "{}.{}".format(self.header_prefix, key)

    def get_message_headers(self, worker_ctx):
        data = worker_ctx.context_data

        if None in data.values():
            warnings.warn(
                "尝试发布无法序列化的头部值。 "
                "值为 `None` 的头部将从有效负载中丢弃。",
                UserWarning,
            )

        headers = {
            self._get_header_name(key): value
            for key, value in data.items()
            if value is not None
        }
        return headers


class HeaderDecoder(object):
    header_prefix = HEADER_PREFIX

    def _strip_header_name(self, key):
        full_prefix = "{}.".format(self.header_prefix)
        if key.startswith(full_prefix):
            return key[len(full_prefix) :]
        return key

    def unpack_message_headers(self, message):
        stripped = {
            self._strip_header_name(k): v for k, v in six.iteritems(message.headers)
        }
        return stripped


class Publisher(DependencyProvider, HeaderEncoder):
    publisher_cls = PublisherCore

    def __init__(self, exchange=None, queue=None, declare=None, **options):
        """提供通过依赖注入的 AMQP 消息发布方法。

        在 AMQP 中，消息被发布到 *交换机*，并路由到绑定的 *队列*。该依赖接受要发布的 `exchange`，并确保在发布之前已声明。

        可选地，您可以使用 `declare` 关键字参数传递其他 :class:`kombu.Exchange` 或 :class:`kombu.Queue` 对象，以便在发布之前进行声明。

        :Parameters:
            exchange : :class:`kombu.Exchange`
                目标交换机
            queue : :class:`kombu.Queue`
                **已弃用**: 绑定队列。事件将发布到该队列的交换机。
            declare : list
                要在发布之前声明的 :class:`kombu.Exchange` 或 :class:`kombu.Queue` 对象的列表。

        如果未提供 `exchange`，则消息将发布到默认交换机。

        示例::

            class Foobar(object):

                publish = Publisher(exchange=...)

                def spam(self, data):
                    self.publish('spam:' + data)
        """
        self.exchange = exchange
        self.options = options

        self.declare = declare[:] if declare is not None else []

        if self.exchange:
            self.declare.append(self.exchange)

        if queue is not None:
            warnings.warn(
                "Publisher 的签名已更改。`queue` 参数现在已弃用。您可以使用 `declare` 参数 "
                "提供要声明的 Kombu 队列的列表。"
                "有关详细信息，请参见 CHANGES，第 2.7.0 版。该警告将在第 2.9.0 版中删除。",
                DeprecationWarning,
            )
            if exchange is None:
                self.exchange = queue.exchange
            self.declare.append(queue)

        # 向后兼容
        compat_attrs = ("retry", "retry_policy", "use_confirms")

        for compat_attr in compat_attrs:
            if hasattr(self, compat_attr):
                warnings.warn(
                    "'{}' 应在实例化时指定，而不是作为类属性。请参见 CHANGES，第 2.7.0 版 "
                    "有关更多详细信息。该警告将在第 2.9.0 版中删除。".format(
                        compat_attr
                    ),
                    DeprecationWarning,
                )
                self.options[compat_attr] = getattr(self, compat_attr)

    @property
    def amqp_uri(self):
        return self.container.config[AMQP_URI_CONFIG_KEY]

    @property
    def serializer(self):
        """默认序列化器，用于发布消息。

        必须作为 `kombu serializer <http://bit.do/kombu_serialization>`_ 注册。
        """
        return self.container.serializer

    def setup(self):
        ssl = self.container.config.get(AMQP_SSL_CONFIG_KEY)
        login_method = self.container.config.get(LOGIN_METHOD_CONFIG_KEY)
        with get_connection(self.amqp_uri, ssl) as conn:
            for entity in self.declare:
                maybe_declare(entity, conn.channel())

        serializer = self.options.pop("serializer", self.serializer)

        self.publisher = self.publisher_cls(
            self.amqp_uri,
            serializer=serializer,
            exchange=self.exchange,
            declare=self.declare,
            ssl=ssl,
            login_method=login_method,
            **self.options,
        )

    def get_dependency(self, worker_ctx):
        extra_headers = self.get_message_headers(worker_ctx)

        def publish(msg, **kwargs):
            self.publisher.publish(msg, extra_headers=extra_headers, **kwargs)

        return publish


class QueueConsumer(SharedExtension, ProviderCollector, ConsumerMixin):
    def __init__(self):
        self._consumers = {}
        self._pending_remove_providers = {}

        self._gt = None
        self._starting = False

        self._consumers_ready = Event()
        super(QueueConsumer, self).__init__()

    @property
    def amqp_uri(self):
        return self.container.config[AMQP_URI_CONFIG_KEY]

    @property
    def prefetch_count(self):
        return self.container.max_workers

    @property
    def accept(self):
        return self.container.accept

    def _handle_thread_exited(self, gt):
        exc = None
        try:
            gt.wait()
        except Exception as e:
            exc = e

        if not self._consumers_ready.ready():
            self._consumers_ready.send_exception(exc)

    def start(self):
        if not self._starting:
            self._starting = True

            _log.debug("启动中 %s", self)
            self._gt = self.container.spawn_managed_thread(self.run)
            self._gt.link(self._handle_thread_exited)

        try:
            _log.debug("等待消费者准备 %s", self)
            self._consumers_ready.wait()
        except QueueConsumerStopped:
            _log.debug("消费者在启动前已停止 %s", self)
        except Exception as exc:
            _log.debug("消费者启动失败 %s (%s)", self, exc)
        else:
            _log.debug("已启动 %s", self)

    def stop(self):
        """优雅地停止队列消费者。

        等待最后一个提供者注销，并等待 ConsumerMixin 的绿色线程退出（即直到所有待处理消息都已确认或重新排队，所有消费者停止）。
        """
        if not self._consumers_ready.ready():
            _log.debug("在消费者启动时尝试停止 %s", self)

            stop_exc = QueueConsumerStopped()
            self._gt.kill(stop_exc)

        self.wait_for_providers()

        try:
            _log.debug("等待消费者退出 %s", self)
            self._gt.wait()
        except QueueConsumerStopped:
            pass

        super(QueueConsumer, self).stop()
        _log.debug("已停止 %s", self)

    def kill(self):
        """强制终止队列消费者。

        与 `stop()` 不同，任何未确认的消息或重新排队请求、移除提供者的请求等都会丢失，消费线程会尽快终止。
        """
        if self._gt is not None and not self._gt.dead:
            self._providers = set()
            self._pending_remove_providers = {}
            self.should_stop = True
            try:
                self._gt.wait()
            except Exception as exc:
                # 忽略异常，因为我们已经在被终止
                _log.warn("QueueConsumer %s 在被杀死时抛出了 `%s`", self, exc)

            super(QueueConsumer, self).kill()
            _log.debug("已杀死 %s", self)

    def unregister_provider(self, provider):
        if not self._consumers_ready.ready():
            # 我们无法处理启动时想要移除消费者的情况
            self._last_provider_unregistered.send()
            return

        removed_event = Event()
        # 我们只能在消费者线程中取消消费者
        self._pending_remove_providers[provider] = removed_event
        # 注册消费者以便被取消
        removed_event.wait()

        super(QueueConsumer, self).unregister_provider(provider)

    def ack_message(self, message):
        # 只有在消息连接仍然活跃时才尝试确认消息；
        # 否则，消息将已经被代理回收
        if message.channel.connection:
            try:
                message.ack()
            except ConnectionError:  # pragma: no cover
                pass  # 忽略连接在条件语句内关闭的情况

    def requeue_message(self, message):
        # 只有在消息连接仍然活跃时才尝试重新排队消息；
        # 否则，消息将已经被代理回收
        if message.channel.connection:
            try:
                message.requeue()
            except ConnectionError:  # pragma: no cover
                pass  # 忽略连接在条件语句内关闭的情况

    def _cancel_consumers_if_requested(self):
        provider_remove_events = self._pending_remove_providers.items()
        self._pending_remove_providers = {}

        for provider, removed_event in provider_remove_events:
            consumer = self._consumers.pop(provider)

            _log.debug("正在取消消费者 [%s]: %s", provider, consumer)
            consumer.cancel()
            removed_event.send()

    @property
    def connection(self):
        """提供 Kombu 的 ConsumerMixin 所需的连接参数。

        `Connection` 对象是连接参数的声明，采用懒加载方式进行评估。
        此时，它并不表示与代理的已建立连接。
        """
        heartbeat = self.container.config.get(HEARTBEAT_CONFIG_KEY, DEFAULT_HEARTBEAT)
        transport_options = self.container.config.get(
            TRANSPORT_OPTIONS_CONFIG_KEY, DEFAULT_TRANSPORT_OPTIONS
        )
        ssl = self.container.config.get(AMQP_SSL_CONFIG_KEY)
        login_method = self.container.config.get(LOGIN_METHOD_CONFIG_KEY)
        conn = Connection(
            self.amqp_uri,
            transport_options=transport_options,
            heartbeat=heartbeat,
            ssl=ssl,
            login_method=login_method,
        )

        return conn

    def handle_message(self, provider, body, message):
        ident = "{}.handle_message[{}]".format(
            type(provider).__name__, message.delivery_info["routing_key"]
        )
        self.container.spawn_managed_thread(
            partial(provider.handle_message, body, message), identifier=ident
        )

    def get_consumers(self, consumer_cls, channel):
        """Kombu 回调，用于设置消费者。

        在与代理的任何（重新）连接之后调用。
        """
        _log.debug("正在设置消费者 %s", self)

        for provider in self._providers:
            callbacks = [partial(self.handle_message, provider)]

            consumer = consumer_cls(
                queues=[provider.queue], callbacks=callbacks, accept=self.accept
            )
            consumer.qos(prefetch_count=self.prefetch_count)

            self._consumers[provider] = consumer

        return self._consumers.values()

    def on_iteration(self):
        """Kombu 回调，在每次 `drain_events` 循环迭代时调用。"""
        self._cancel_consumers_if_requested()

        if len(self._consumers) == 0:
            _log.debug("迭代后请求停止")
            self.should_stop = True

    def on_connection_error(self, exc, interval):
        _log.warning(
            "连接到代理时发生错误：{}（{}）。\n将在{}秒后重试。".format(
                sanitize_url(self.amqp_uri), exc, interval
            )
        )

    def on_consume_ready(self, connection, channel, consumers, **kwargs):
        """Kombu 回调，当消费者准备好接受消息时调用。

        在与代理的任何（重新）连接之后调用。
        """
        if not self._consumers_ready.ready():
            _log.debug("消费者已启动 %s", self)
            self._consumers_ready.send(None)


class Consumer(Entrypoint, HeaderDecoder):
    queue_consumer = QueueConsumer()

    def __init__(self, queue, requeue_on_error=False, **kwargs):
        """
        装饰器将方法标记为消息消费者。

        来自队列的消息将根据其内容类型进行反序列化，并传递给被装饰的方法。
        当消费者方法正常返回且没有引发任何异常时，消息将自动确认。
        如果在消费过程中引发任何异常，并且 `requeue_on_error` 为 `True`，消息将被重新入队。

        如果 `requeue_on_error` 为真，当处理事件时发生错误时，处理程序将返回事件到队列。默认值为假。

        示例::

            @consume(...)
            def handle_message(self, body):

                if not self.spam(body):
                    raise Exception('消息将被重新入队')

                self.shrub(body)

        参数:
            queue: 要消费的队列。
        """
        self.queue = queue
        self.requeue_on_error = requeue_on_error
        super(Consumer, self).__init__(**kwargs)

    def setup(self):
        self.queue_consumer.register_provider(self)

    def stop(self):
        self.queue_consumer.unregister_provider(self)

    def handle_message(self, body, message):
        args = (body,)
        kwargs = {}

        context_data = self.unpack_message_headers(message)

        handle_result = partial(self.handle_result, message)
        try:
            self.container.spawn_worker(
                self,
                args,
                kwargs,
                context_data=context_data,
                handle_result=handle_result,
            )
        except ContainerBeingKilled:
            self.queue_consumer.requeue_message(message)

    def handle_result(self, message, worker_ctx, result=None, exc_info=None):
        self.handle_message_processed(message, result, exc_info)
        return result, exc_info

    def handle_message_processed(self, message, result=None, exc_info=None):
        if exc_info is not None and self.requeue_on_error:
            self.queue_consumer.requeue_message(message)
        else:
            self.queue_consumer.ack_message(message)


consume = Consumer.decorator


class QueueConsumerStopped(Exception):
    pass
