"""
提供了对核心消息模块的高级接口。

事件是特殊的消息，可以由一个服务发出，并由其他监听服务处理。

事件由一个标识符和一些数据组成，并使用从 :class:`EventDispatcher` 实例获得的注入进行调度。

事件是异步调度的。仅保证事件已被调度，并不保证它被监听器接收或处理。

要监听事件，服务必须使用 :func:`handle_event` 入口点声明一个处理程序，提供目标服务和事件类型过滤器。

示例::

    # 服务 A
    def edit_foo(self, id):
        # ...
        self.dispatch('foo_updated', {'id': id})

    # 服务 B

    @handle_event('service_a', 'foo_updated')
    def bar(event_data):
        pass

"""

from __future__ import absolute_import

import uuid
from logging import getLogger

from kombu import Queue

from nameko.messaging import Consumer, Publisher
from nameko.standalone.events import get_event_exchange


SERVICE_POOL = "service_pool"
SINGLETON = "singleton"
BROADCAST = "broadcast"

_log = getLogger(__name__)


class EventHandlerConfigurationError(Exception):
    """当事件处理程序配置错误时引发的异常。"""


class EventDispatcher(Publisher):
    """通过依赖注入提供事件调度方法。

    发出的事件将通过服务的事件交换进行调度，
    该交换会自动声明为主题交换。
    交换的名称将是 `{service-name}.events`。

    通过调度器发出的事件将被序列化并发布到事件交换。
    事件的类型属性用作路由键，可用于在监听器端进行过滤。

    调度器将在事件消息发布后立即返回。
    不保证任何服务会接收事件，仅保证事件已成功调度。

    示例::

        class Spammer(object):
            dispatch_spam = EventDispatcher()

            def emit_spam(self):
                evt_data = '火腿和鸡蛋'
                self.dispatch_spam('spam.ham', evt_data)

    """

    def setup(self):
        self.exchange = get_event_exchange(
            self.container.service_name, self.container.config
        )
        self.declare.append(self.exchange)
        super(EventDispatcher, self).setup()

    def get_dependency(self, worker_ctx):
        """在服务实例上注入一个调度方法"""
        extra_headers = self.get_message_headers(worker_ctx)

        def dispatch(event_type, event_data):
            self.publisher.publish(
                event_data,
                exchange=self.exchange,
                routing_key=event_type,
                extra_headers=extra_headers,
            )

        return dispatch


class EventHandler(Consumer):
    def __init__(
        self,
        source_service,
        event_type,
        handler_type=SERVICE_POOL,
        reliable_delivery=True,
        requeue_on_error=False,
        **kwargs,
    ):
        """
        将方法装饰为处理来自名为 ``source_service`` 的服务的 ``event_type`` 事件的处理程序。
        
        :Parameters:

            source_service : str
                发出事件的服务名称
            event_type : str
                要处理的事件类型
            handler_type : str
                决定处理程序在集群中的行为:

                - ``events.SERVICE_POOL``:
                    事件处理程序按服务类型和方法进行池化，
                    每个池中的一个服务实例接收事件。 ::
                                   .-[队列]- (服务 X 处理方法-1)
                                  /
                        交换 o --[队列]- (服务 X 处理方法-2)
                                  \\
                                   \\          (服务 Y（实例 1）处理方法)
                                    \\       /
                                     [队列]
                                            \\
                                              (服务 Y（实例 2）处理方法)
                - ``events.SINGLETON``:
                    事件仅由一个注册的处理程序接收，
                    不管服务类型如何。如果在错误时重新排队，它们可能
                    会被不同的服务实例处理。 ::
                                               (服务 X 处理方法)
                                             /
                        交换 o -- [队列]
                                             \\
                                               (服务 Y 处理方法)
                - ``events.BROADCAST``:
                    事件将被每个处理程序接收。事件广播到每个服务实例，而不仅仅是每个服务
                    类型。实例通过 :attr:`EventHandler.broadcast_identifier` 进行区分。 ::
                                    [队列]- (服务 X（实例 1）处理方法)
                                  /
                        交换 o - [队列]- (服务 X（实例 2）处理方法)
                                  \\
                                    [队列]- (服务 Y 处理方法)

            requeue_on_error : bool  # TODO: 由 Consumer 定义..
                如果为真，则如果处理事件时发生错误，处理程序将事件返回到队列。
                默认值为 False。
            reliable_delivery : bool
                如果为真，事件将在队列中保持，直到有处理程序来消费它们。默认值为 True。
        """
        self.source_service = source_service
        self.event_type = event_type
        self.handler_type = handler_type
        self.reliable_delivery = reliable_delivery

        super(EventHandler, self).__init__(
            queue=None, requeue_on_error=requeue_on_error, **kwargs
        )

    @property
    def broadcast_identifier(self):
        """
        用于 `BROADCAST` 类型处理程序的唯一字符串，以识别服务实例。

        当使用 `BROADCAST` 处理程序类型时，`broadcast_identifier` 将附加到队列名称。
        它必须唯一地识别接收广播的服务实例。

        默认的 `broadcast_identifier` 是在服务启动时设置的 uuid。
        当服务重新启动时，它会改变，这意味着任何未消费的消息
        将不会被发送到 '旧' 服务实例的 '新' 实例接收。 ::

            @property
            def broadcast_identifier(self):
                # 使用 uuid 作为标识符。
                # 当服务重新启动时，标识符将会改变，任何未消费的消息将会丢失
                return uuid.uuid4().hex

        因此，默认行为与可靠交付不兼容。

        一个能够在服务重启时存活的替代 `broadcast_identifier` 是 ::

            @property
            def broadcast_identifier(self):
                # 使用机器的主机名作为标识符。
                # 这假设在任何给定机器上仅运行一个服务实例
                return socket.gethostname()

        如果这两种方法都不合适，可以从配置文件中读取该值 ::

            @property
            def broadcast_identifier(self):
                return self.config['SERVICE_IDENTIFIER']  # 或类似的

        广播队列是独占的，以确保 `broadcast_identifier` 值是唯一的。

        由于此方法是描述符，它将在容器创建期间被调用，
        与配置的 `handler_type` 无关。
        有关更多详细信息，请参见 :class:`nameko.extensions.Extension`。
        """
        if self.handler_type is not BROADCAST:
            return None

        if self.reliable_delivery:
            raise EventHandlerConfigurationError(
                "您正在使用默认的广播标识符，"
                "这与可靠交付不兼容。请参阅 "
                ":meth:`nameko.events.EventHandler.broadcast_identifier` "
                "以获取详细信息。"
            )

        return uuid.uuid4().hex

    def setup(self):
        _log.debug("启动 %s", self)

        # handler_type 决定队列名称和独占标志
        exclusive = False
        service_name = self.container.service_name
        if self.handler_type is SERVICE_POOL:
            queue_name = "evt-{}-{}--{}.{}".format(
                self.source_service, self.event_type, service_name, self.method_name
            )
        elif self.handler_type is SINGLETON:
            queue_name = "evt-{}-{}".format(self.source_service, self.event_type)
        elif self.handler_type is BROADCAST:
            broadcast_identifier = self.broadcast_identifier
            queue_name = "evt-{}-{}--{}.{}-{}".format(
                self.source_service,
                self.event_type,
                service_name,
                self.method_name,
                broadcast_identifier,
            )

        exchange = get_event_exchange(self.source_service, self.container.config)

        # 对于没有可靠交付的处理程序，队列应标记为自动删除，以便在消费者断开连接时被移除
        auto_delete = self.reliable_delivery is False

        # 对于广播处理程序，队列是独占的（这意味着只有一个消费者可以连接）
        # 除非启用了可靠交付，因为独占队列在消费者断开连接时
        # 始终被移除，而不管 auto_delete 的值如何
        exclusive = self.handler_type is BROADCAST
        if self.reliable_delivery:
            exclusive = False

        self.queue = Queue(
            queue_name,
            exchange=exchange,
            routing_key=self.event_type,
            durable=True,
            auto_delete=auto_delete,
            exclusive=exclusive,
        )

        super(EventHandler, self).setup()


event_handler = EventHandler.decorator
