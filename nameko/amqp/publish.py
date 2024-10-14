import warnings
from contextlib import contextmanager

from kombu import Connection
from kombu.exceptions import ChannelError
from kombu.pools import connections, producers

from nameko.constants import (
    DEFAULT_RETRY_POLICY, DEFAULT_TRANSPORT_OPTIONS, PERSISTENT
)


class UndeliverableMessage(Exception):
    """ 当启用了发布者确认并且消息无法路由或持久存储时抛出的异常。
    """
    pass


@contextmanager
def get_connection(amqp_uri, ssl=None, login_method=None, transport_options=None):
    if not transport_options:
        transport_options = DEFAULT_TRANSPORT_OPTIONS.copy()
    conn = Connection(
        amqp_uri, transport_options=transport_options, ssl=ssl,
        login_method=login_method
    )

    with connections[conn].acquire(block=True) as connection:
        yield connection


@contextmanager
def get_producer(
    amqp_uri, confirms=True, ssl=None, login_method=None, transport_options=None
):
    if transport_options is None:
        transport_options = DEFAULT_TRANSPORT_OPTIONS.copy()
    transport_options['confirm_publish'] = confirms
    conn = Connection(
        amqp_uri, transport_options=transport_options, ssl=ssl,
        login_method=login_method
    )

    with producers[conn].acquire(block=True) as producer:
        yield producer


class Publisher(object):
    """
    用于向 RabbitMQ 发布消息的工具助手。
    """

    use_confirms = True
    """
    为该发布者启用 `confirms <http://www.rabbitmq.com/confirms.html>`_ 。

    发布者将等待来自代理的确认，以确保消息已被接收并适当处理，否则将抛出异常。启用确认会带来性能损耗，但可以保证消息不会丢失，例如由于连接过期导致的丢失。
    """

    transport_options = DEFAULT_TRANSPORT_OPTIONS.copy()
    """一个用于传递给其他 Kombu 通道实现的附加连接参数的字典。请参考传输文档以了解可用的选项。
    """

    delivery_mode = PERSISTENT
    """
    此发布者发布消息的默认投递模式。
    """

    mandatory = False
    """
    要求为发布的消息启用 `mandatory <https://www.rabbitmq.com/amqp-0-9-1-reference.html#basic.publish.mandatory>`_ 投递。
    """

    priority = 0
    """
    发布消息的优先级值，与 `消费者优先级 <https://www.rabbitmq.com/priority.html>`_ 配合使用 。
    """

    expiration = None
    """
    每条消息的 TTL(存活时间), 单位为毫秒。详见 `每条消息 TTL <https://www.rabbitmq.com/ttl.html>`_ 。
    """

    serializer = "json"
    """
    发布消息时使用的序列化器名称。

    必须注册为 `kombu 序列化器 <http://bit.do/kombu_serialization>`_ 。
    """

    compression = None
    """
    发布消息时使用的压缩方式名称。

    必须注册为 `kombu 压缩工具 <http://bit.do/kombu-compression>`_ 。
    """

    retry = True
    """
    启用自动重试，当由于连接错误导致消息发布失败时。

    根据 :attr:`self.retry_policy` 执行重试。
    """

    retry_policy = DEFAULT_RETRY_POLICY
    """
    重试发布消息时应用的策略（如果请求重试）。

    参见 :attr:`self.retry` 。
    """

    declare = []
    """
    在发布消息前需要（重新）声明的 Kombu 对象，如 :class:`~kombu.messaging.Queue` 或 :class:`~kombu.messaging.Exchange` 。
    """

    def __init__(
        self, amqp_uri, use_confirms=None, serializer=None, compression=None,
        delivery_mode=None, mandatory=None, priority=None, expiration=None,
        declare=None, retry=None, retry_policy=None, ssl=None, login_method=None,
        **publish_kwargs
    ):
        self.amqp_uri = amqp_uri
        self.ssl = ssl
        self.login_method = login_method

        # 发布确认
        if use_confirms is not None:
            self.use_confirms = use_confirms

        # 投递选项
        if delivery_mode is not None:
            self.delivery_mode = delivery_mode
        if mandatory is not None:
            self.mandatory = mandatory
        if priority is not None:
            self.priority = priority
        if expiration is not None:
            self.expiration = expiration

        # 消息选项
        if serializer is not None:
            self.serializer = serializer
        if compression is not None:
            self.compression = compression

        # 重试策略
        if retry is not None:
            self.retry = retry
        if retry_policy is not None:
            self.retry_policy = retry_policy

        # 声明
        if declare is not None:
            self.declare = declare

        # 其他发布参数
        self.publish_kwargs = publish_kwargs

    def publish(self, payload, **kwargs):
        """ 发布一条消息
        """
        publish_kwargs = self.publish_kwargs.copy()

        # 合并发布者实例化时的头信息与现在提供的任何头信息；“额外”的头信息总是优先。
        headers = publish_kwargs.pop('headers', {}).copy()
        headers.update(kwargs.pop('headers', {}))
        headers.update(kwargs.pop('extra_headers', {}))

        use_confirms = kwargs.pop('use_confirms', self.use_confirms)
        transport_options = kwargs.pop('transport_options',
                                       self.transport_options
                                       )
        transport_options['confirm_publish'] = use_confirms

        delivery_mode = kwargs.pop('delivery_mode', self.delivery_mode)
        mandatory = kwargs.pop('mandatory', self.mandatory)
        priority = kwargs.pop('priority', self.priority)
        expiration = kwargs.pop('expiration', self.expiration)
        serializer = kwargs.pop('serializer', self.serializer)
        compression = kwargs.pop('compression', self.compression)
        retry = kwargs.pop('retry', self.retry)
        retry_policy = kwargs.pop('retry_policy', self.retry_policy)

        declare = self.declare[:]
        declare.extend(kwargs.pop('declare', ()))

        publish_kwargs.update(kwargs)  # 剩余的在发布时传递的关键字参数优先。

        with get_producer(self.amqp_uri,
                          use_confirms,
                          self.ssl,
                          self.login_method,
                          transport_options,
                          ) as producer:
            try:
                producer.publish(
                    payload,
                    headers=headers,
                    delivery_mode=delivery_mode,
                    mandatory=mandatory,
                    priority=priority,
                    expiration=expiration,
                    compression=compression,
                    declare=declare,
                    retry=retry,
                    retry_policy=retry_policy,
                    serializer=serializer,
                    **publish_kwargs
                )
            except ChannelError as exc:
                if "NO_ROUTE" in str(exc):
                    raise UndeliverableMessage()
                raise

            if mandatory:
                if not use_confirms:
                    warnings.warn(
                        "Mandatory delivery was requested, but "
                        "unroutable messages cannot be detected without "
                        "publish confirms enabled."
                    )
