from __future__ import absolute_import, unicode_literals

import sys
import uuid
import warnings
from functools import partial
from logging import getLogger
from typing import Optional

import kombu.serialization
from eventlet.event import Event
from kombu import Exchange, Queue

from nameko.amqp.publish import Publisher, UndeliverableMessage
from nameko.constants import (
    AMQP_SSL_CONFIG_KEY,
    AMQP_URI_CONFIG_KEY,
    DEFAULT_SERIALIZER,
    LOGIN_METHOD_CONFIG_KEY,
    RPC_EXCHANGE_CONFIG_KEY,
    SERIALIZER_CONFIG_KEY,
)
from nameko.exceptions import (
    ContainerBeingKilled,
    MalformedRequest,
    MethodNotFound,
    UnknownService,
    UnserializableValueError,
    deserialize,
    serialize,
)
from nameko.extensions import (
    DependencyProvider,
    Entrypoint,
    ProviderCollector,
    SharedExtension,
)
from nameko.messaging import HeaderDecoder, HeaderEncoder, QueueConsumer


_log = getLogger(__name__)


RPC_QUEUE_TEMPLATE = "rpc-{}"
RPC_REPLY_QUEUE_TEMPLATE = "rpc.reply-{}-{}"
RPC_REPLY_QUEUE_TTL = 300000  # ms (5 mins)


def get_rpc_exchange(config):
    exchange_name = config.get(RPC_EXCHANGE_CONFIG_KEY, "nameko-rpc")
    exchange = Exchange(exchange_name, durable=True, type="topic")
    return exchange


class RpcConsumer(SharedExtension, ProviderCollector):
    queue_consumer = QueueConsumer()

    def __init__(self):
        self._unregistering_providers = set()
        self._unregistered_from_queue_consumer = Event()
        self.queue = None
        super(RpcConsumer, self).__init__()

    def setup(self):
        if self.queue is None:
            service_name = self.container.service_name
            queue_name = RPC_QUEUE_TEMPLATE.format(service_name)
            routing_key = "{}.*".format(service_name)

            exchange = get_rpc_exchange(self.container.config)

            self.queue = Queue(
                queue_name, exchange=exchange, routing_key=routing_key, durable=True
            )

            self.queue_consumer.register_provider(self)
            self._registered = True

    def stop(self):
        """停止 RpcConsumer。

        当最后一个 Rpc 子类从队列消费者中注销时，RpcConsumer 将正常注销。如果没有注册任何提供者，则我们应该在被请求停止时立即从队列消费者注销。
        """
        if not self._providers_registered:
            self.queue_consumer.unregister_provider(self)
            self._unregistered_from_queue_consumer.send(True)

    def unregister_provider(self, provider):
        """注销提供者。

        阻塞直到此 RpcConsumer 从其队列消费者中注销，这只有在所有提供者都请求注销时才会发生。
        """
        self._unregistering_providers.add(provider)
        remaining_providers = self._providers - self._unregistering_providers
        if not remaining_providers:
            _log.debug("正在从队列消费者注销 %s", self)
            self.queue_consumer.unregister_provider(self)
            _log.debug("已从队列消费者注销 %s", self)
            self._unregistered_from_queue_consumer.send(True)

        _log.debug("等待从队列消费者注销 %s", self)
        self._unregistered_from_queue_consumer.wait()
        super(RpcConsumer, self).unregister_provider(provider)

    def get_provider_for_method(self, routing_key):
        service_name = self.container.service_name

        for provider in self._providers:
            key = "{}.{}".format(service_name, provider.method_name)
            if key == routing_key:
                return provider
        else:
            method_name = routing_key.split(".")[-1]
            raise MethodNotFound(method_name)

    def handle_message(self, body, message):
        routing_key = message.delivery_info["routing_key"]
        try:
            provider = self.get_provider_for_method(routing_key)
            provider.handle_message(body, message)
        except Exception:
            exc_info = sys.exc_info()
            self.handle_result(message, None, exc_info)

    def handle_result(self, message, result, exc_info):
        amqp_uri = self.container.config[AMQP_URI_CONFIG_KEY]
        serializer = self.container.config.get(
            SERIALIZER_CONFIG_KEY, DEFAULT_SERIALIZER
        )
        exchange = get_rpc_exchange(self.container.config)
        ssl = self.container.config.get(AMQP_SSL_CONFIG_KEY)
        login_method = self.container.config.get(LOGIN_METHOD_CONFIG_KEY)

        responder = Responder(
            amqp_uri, exchange, serializer, message, ssl=ssl, login_method=login_method
        )
        result, exc_info = responder.send_response(result, exc_info)

        self.queue_consumer.ack_message(message)
        return result, exc_info

    def requeue_message(self, message):
        self.queue_consumer.requeue_message(message)


class Rpc(Entrypoint, HeaderDecoder):
    rpc_consumer = RpcConsumer()

    def setup(self):
        self.rpc_consumer.register_provider(self)

    def stop(self):
        self.rpc_consumer.unregister_provider(self)

    def handle_message(self, body, message):
        try:
            args = body["args"]
            kwargs = body["kwargs"]
        except KeyError:
            raise MalformedRequest("Message 缺失 `args` 或 `kwargs`")

        self.check_signature(args, kwargs)

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
            self.rpc_consumer.requeue_message(message)

    def handle_result(self, message, worker_ctx, result, exc_info):
        result, exc_info = self.rpc_consumer.handle_result(message, result, exc_info)
        return result, exc_info


rpc = Rpc.decorator


class Responder(object):
    publisher_cls = Publisher

    def __init__(
        self, amqp_uri, exchange, serializer, message, ssl=None, login_method=None
    ):
        self.amqp_uri = amqp_uri
        self.serializer = serializer
        self.message = message
        self.exchange = exchange
        self.ssl = ssl
        self.login_method = login_method

    def send_response(self, result, exc_info):
        error = None
        if exc_info is not None:
            error = serialize(exc_info[1])

        # 发送以与请求消息相同的方式编码的响应。
        content_type = self.message.properties["content_type"]
        serializer = kombu.serialization.registry.type_to_name[content_type]

        # 灾难避免序列化检查：`result` 必须是可序列化的，
        # 否则容器将假定发生不可恢复的错误而自杀（消息将被重新排队给另一个处理者）。

        try:
            kombu.serialization.dumps(result, serializer)
        except Exception:
            exc_info = sys.exc_info()
            # 下面的 `error` 确保能够序列化为 JSON。
            error = serialize(UnserializableValueError(result))
            result = None

        payload = {"result": result, "error": error}

        routing_key = self.message.properties["reply_to"]
        correlation_id = self.message.properties.get("correlation_id")

        publisher = self.publisher_cls(
            self.amqp_uri, ssl=self.ssl, login_method=self.login_method
        )

        publisher.publish(
            payload,
            serializer=serializer,
            exchange=self.exchange,
            routing_key=routing_key,
            correlation_id=correlation_id,
        )

        return result, exc_info


class ReplyListener(SharedExtension):
    queue_consumer = QueueConsumer()

    def __init__(self, **kwargs):
        self._reply_events = {}
        super(ReplyListener, self).__init__(**kwargs)

    def setup(self):
        reply_queue_uuid = uuid.uuid4()
        service_name = self.container.service_name

        queue_name = RPC_REPLY_QUEUE_TEMPLATE.format(service_name, reply_queue_uuid)

        self.routing_key = str(reply_queue_uuid)

        exchange = get_rpc_exchange(self.container.config)

        self.queue = Queue(
            queue_name,
            exchange=exchange,
            routing_key=self.routing_key,
            queue_arguments={"x-expires": RPC_REPLY_QUEUE_TTL},
        )

        self.queue_consumer.register_provider(self)

    def stop(self):
        self.queue_consumer.unregister_provider(self)
        super(ReplyListener, self).stop()

    def get_reply_event(self, correlation_id):
        reply_event = Event()
        self._reply_events[correlation_id] = reply_event
        return reply_event

    def handle_message(self, body, message):
        self.queue_consumer.ack_message(message)

        correlation_id = message.properties.get("correlation_id")
        client_event = self._reply_events.pop(correlation_id, None)
        if client_event is not None:
            client_event.send(body)
        else:
            _log.debug("Unknown correlation id: %s", correlation_id)


class RpcProxy(DependencyProvider):
    rpc_reply_listener = ReplyListener()

    def __init__(self, target_service, **options):
        self.target_service = target_service
        self.options = options

    def get_dependency(self, worker_ctx):
        return ServiceProxy(
            worker_ctx, self.target_service, self.rpc_reply_listener, **self.options
        )


class ServiceProxy(object):
    def __init__(
        self, worker_ctx, service_name, reply_listener: ReplyListener, **options
    ):
        self.worker_ctx = worker_ctx
        self.service_name = service_name
        self.reply_listener = reply_listener
        self.options = options

    def __getattr__(self, name):
        return MethodProxy(
            self.worker_ctx,
            self.service_name,
            name,
            self.reply_listener,
            **self.options,
        )


class RpcReply(object):
    """解析RPC响应内容"""

    resp_body: Optional[dict] = None

    def __init__(self, reply_event: Event):
        self.reply_event = reply_event

    def result(self):
        _log.debug("等待 RPC 响应事件 %s", self)

        if self.resp_body is None:
            self.resp_body = self.reply_event.wait()  # type: ignore
            _log.debug("RPC 响应事件完成 %s %s", self, self.resp_body)

        if self.resp_body is None:
            raise ValueError("RPC执行结果获取失败")

        error = self.resp_body.get("error")
        if error:
            raise deserialize(error)
        return self.resp_body["result"]


class MethodProxy(HeaderEncoder):
    """RPC 方法代理"""

    publisher_cls = Publisher

    def __init__(
        self,
        worker_ctx,
        service_name,
        method_name,
        reply_listener: ReplyListener,
        **options,
    ):
        """
        请注意，抛出 `UnknownService` 异常的机制依赖于代理中启用发布确认。
        """

        self.worker_ctx = worker_ctx
        self.service_name = service_name
        self.method_name = method_name
        self.reply_listener = reply_listener

        # 向后兼容
        compat_attrs = ("retry", "retry_policy", "use_confirms")

        for compat_attr in compat_attrs:
            if hasattr(self, compat_attr):
                warnings.warn(
                    "'{}' 应在 RpcProxy 实例化时指定，而不是作为类属性。"
                    "有关详细信息，请参阅 CHANGES，第 2.7.0 版。"
                    "此警告将在第 2.9.0 版中删除。".format(compat_attr),
                    DeprecationWarning,
                )
                options[compat_attr] = getattr(self, compat_attr)

        serializer = options.pop("serializer", self.serializer)

        self.publisher = self.publisher_cls(
            self.amqp_uri,
            serializer=serializer,
            ssl=self.ssl,
            login_method=self.login_method,
            **options,
        )

    def __call__(self, *args, **kwargs):
        reply = self._call(*args, **kwargs)
        return reply.result()

    @property
    def container(self):
        # TODO: seems wrong
        return self.worker_ctx.container

    @property
    def amqp_uri(self):
        return self.container.config[AMQP_URI_CONFIG_KEY]

    @property
    def ssl(self):
        return self.container.config.get(AMQP_SSL_CONFIG_KEY)

    @property
    def login_method(self):
        return self.container.config.get(LOGIN_METHOD_CONFIG_KEY)

    @property
    def serializer(self):
        """用于发布消息有效负载时的默认序列化器。

        必须作为一个
        `kombu 序列化器 <http://bit.do/kombu_serialization>`_ 注册。
        """
        return self.container.config.get(SERIALIZER_CONFIG_KEY, DEFAULT_SERIALIZER)

    def call_async(self, *args, **kwargs):
        reply = self._call(*args, **kwargs)
        return reply

    def _call(self, *args, **kwargs):
        _log.debug("调用 %s", self)

        msg = {"args": args, "kwargs": kwargs}

        # 我们在下面的 `producer.publish` 中使用 `mandatory` 标志来捕捉
        # 对不存在服务的 rpc 调用，否则会无限等待一个不会到来的回复。
        #
        # 然而，basic.return（“没有人监听该主题”）是异步发送的
        # 并且有条件的，因此我们无法在通道上等待它
        # （在成功交付时会无限等待）。
        #
        # 相反，我们利用（rabbitmq 扩展）confirm_publish
        # (https://www.rabbitmq.com/confirms.html)，这总是
        # 通过通道发送回复。此外，在没有队列
        # 绑定到交换机的情况下（服务未知），basic.return 首先发送，
        # 因此当 kombu 返回（在等待确认后）时
        # 我们可以可靠地检查返回的消息。

        # 请注意，在 RpcProxy 中停用发布确认将禁用
        # 此功能，因此 :class:`UnknownService` 将永远不会
        # 被引发（并且调用者将挂起）。

        exchange = get_rpc_exchange(self.container.config)
        routing_key = "{}.{}".format(self.service_name, self.method_name)

        reply_to = self.reply_listener.routing_key
        correlation_id = str(uuid.uuid4())

        extra_headers = self.get_message_headers(self.worker_ctx)

        reply_event = self.reply_listener.get_reply_event(correlation_id)

        try:
            self.publisher.publish(
                msg,
                exchange=exchange,
                routing_key=routing_key,
                mandatory=True,
                reply_to=reply_to,
                correlation_id=correlation_id,
                extra_headers=extra_headers,
            )
        except UndeliverableMessage:
            raise UnknownService(self.service_name)

        return RpcReply(reply_event)

    def __repr__(self):
        service_name = self.service_name
        method_name = self.method_name
        return "<proxy method: {}.{}>".format(service_name, method_name)
