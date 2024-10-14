import json
import uuid
from collections import namedtuple
from functools import partial
from logging import getLogger

import six
import werkzeug
from eventlet.event import Event
from eventlet.websocket import WebSocketWSGI
from packaging import version
from werkzeug.routing import Rule

from nameko.exceptions import (
    ConnectionNotFound, MalformedRequest, MethodNotFound, serialize
)
from nameko.extensions import (
    DependencyProvider, Entrypoint, ProviderCollector, SharedExtension
)
from nameko.web.server import WebServer


# 在 2.0.0 版本中，Werkzeug 开始正确识别传入的 WebSocket 请求，
# 并仅将其匹配到标记为 WebSocket 目标的规则。
# 请参见 `GitHub issue #2052 <https://github.com/pallets/werkzeug/issues/2052>`_ 。
# 所有版本的 Werkzeug 在没有规则匹配时都会抛出 400 Bad Request 错误，
# 因此我们需要根据 Werkzeug 的版本对规则的显式标识作为 WebSocket 目标进行条件判断。
IDENTIFY_WEBSOCKET_RULES = version.parse(werkzeug.__version__) >= version.parse("2.0.0")


_log = getLogger(__name__)


SocketInfo = namedtuple('SocketInfo', ['socket', 'data'])


class Connection(object):

    def __init__(self, socket_id, context_data):
        self.socket_id = socket_id
        self.context_data = context_data
        self.subscriptions = set()


class WebSocketServer(SharedExtension, ProviderCollector):
    wsgi_server = WebServer()

    def __init__(self):
        super(WebSocketServer, self).__init__()
        self.sockets = {}

    def deserialize_ws_frame(self, payload):
        try:
            data = json.loads(payload)
            return (
                data['method'],
                data.get('data') or {},
                data.get('correlation_id'),
            )
        except Exception:
            raise MalformedRequest('Invalid JSON data')

    def serialize_for_ws(self, payload):
        return six.text_type(json.dumps(payload))

    def serialize_event(self, event, data):
        return self.serialize_for_ws({
            'type': 'event',
            'event': event,
            'data': data,
        })

    def get_url_rule(self):
        return Rule('/ws', methods=['GET'], websocket=IDENTIFY_WEBSOCKET_RULES)

    def handle_request(self, request):
        context_data = self.wsgi_server.context_data_from_headers(request)
        return self.websocket_mainloop(context_data)

    def websocket_mainloop(self, initial_context_data):
        def handler(ws):
            socket_id, context_data = self.add_websocket(
                ws, initial_context_data)
            try:
                ws.send(self.serialize_event(
                    'connected', {'socket_id': socket_id})
                )

                while 1:
                    raw_req = ws.wait()
                    if raw_req is None:
                        break
                    ws.send(self.handle_websocket_request(
                        socket_id, context_data, raw_req))
            finally:
                self.remove_socket(socket_id)
        return WebSocketWSGI(handler)

    def handle_websocket_request(self, socket_id, context_data, raw_req):
        correlation_id = None
        try:
            method, data, correlation_id = self.deserialize_ws_frame(
                raw_req)
            provider = self.get_provider_for_method(method)
            result = provider.handle_message(socket_id, data, context_data)
            response = {
                'type': 'result',
                'success': True,
                'data': result,
                'correlation_id': correlation_id,
            }

        except Exception as exc:
            error = serialize(exc)
            response = {
                'type': 'result',
                'success': False,
                'error': error,
                'correlation_id': correlation_id,
            }

        return self.serialize_for_ws(response)

    def get_provider_for_method(self, method):
        for provider in self._providers:
            if (
                isinstance(provider, WebSocketRpc) and
                provider.method_name == method
            ):
                return provider
        raise MethodNotFound()

    def setup(self):
        self.wsgi_server.register_provider(self)

    def stop(self):
        self.wsgi_server.unregister_provider(self)
        super(WebSocketServer, self).stop()

    def add_websocket(self, ws, initial_context_data=None):
        socket_id = str(uuid.uuid4())
        context_data = dict(initial_context_data or ())
        self.sockets[socket_id] = SocketInfo(ws, context_data)
        return socket_id, context_data

    def remove_socket(self, socket_id):
        self.sockets.pop(socket_id, None)
        for provider in self._providers:
            if isinstance(provider, WebSocketHubProvider):
                provider.cleanup_websocket(socket_id)


class WebSocketHubProvider(DependencyProvider):
    hub = None
    server = WebSocketServer()

    def setup(self):
        self.hub = WebSocketHub(self.server)
        self.server.register_provider(self)

    def stop(self):
        self.server.unregister_provider(self)
        super(WebSocketHubProvider, self).stop()

    def get_dependency(self, worker_ctx):
        return self.hub

    def cleanup_websocket(self, socket_id):
        con = self.hub.connections.pop(socket_id, None)
        if con is not None:
            for channel in con.subscriptions:
                subs = self.hub.subscriptions.get(channel)
                if subs:
                    subs.discard(socket_id)


class WebSocketHub(object):

    def __init__(self, server):
        self._server = server
        self.connections = {}
        self.subscriptions = {}

    def _get_connection(self, socket_id, create=True):
        rv = self.connections.get(socket_id)
        if rv is not None:
            return rv
        rv = self._server.sockets.get(socket_id)
        if rv is None:
            if not create:
                return None
            raise ConnectionNotFound(socket_id)
        if not create:
            return None
        _, context_data = rv
        self.connections[socket_id] = rv = Connection(socket_id, context_data)
        return rv

    def get_subscriptions(self, socket_id):
        """返回套接字的所有订阅列表。"""
        con = self._get_connection(socket_id, create=False)
        if con is None:
            return []
        return sorted(con.subscriptions)

    def subscribe(self, socket_id, channel):
        """将套接字订阅到频道。"""
        con = self._get_connection(socket_id)
        self.subscriptions.setdefault(channel, set()).add(socket_id)
        con.subscriptions.add(channel)

    def unsubscribe(self, socket_id, channel):
        """将套接字从频道中取消订阅。"""
        con = self._get_connection(socket_id, create=False)
        if con is not None:
            con.subscriptions.discard(channel)
        try:
            self.subscriptions[channel].discard(socket_id)
        except KeyError:
            pass

    def broadcast(self, channel, event, data):
        """向所有在频道上监听的套接字广播事件。"""
        payload = self._server.serialize_event(event, data)
        for socket_id in self.subscriptions.get(channel, ()):
            rv = self._server.sockets.get(socket_id)
            if rv is not None:
                rv.socket.send(payload)

    def unicast(self, socket_id, event, data):
        """向单个套接字发送事件。如果成功则返回 `True`，否则返回 `False`。
        """
        payload = self._server.serialize_event(event, data)
        rv = self._server.sockets.get(socket_id)
        if rv is not None:
            rv.socket.send(payload)
            return True
        return False


class WebSocketRpc(Entrypoint):
    server = WebSocketServer()

    def setup(self):
        self.server.register_provider(self)

    def stop(self):
        self.server.unregister_provider(self)
        super(WebSocketRpc, self).stop()

    def handle_message(self, socket_id, data, context_data):
        self.check_signature((socket_id,), data)
        event = Event()
        self.container.spawn_worker(self, (socket_id,), data,
                                    context_data=context_data,
                                    handle_result=partial(
                                        self.handle_result, event))
        return event.wait()

    def handle_result(self, event, worker_ctx, result, exc_info):
        event.send(result, exc_info)
        return result, exc_info


rpc = WebSocketRpc.decorator
