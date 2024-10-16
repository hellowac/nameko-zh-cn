import re
import socket
from collections import namedtuple
from functools import partial
from logging import getLogger

import eventlet
from eventlet import wsgi
from eventlet.support import get_errno
from eventlet.wsgi import BROKEN_SOCK, BaseHTTPServer, HttpProtocol
from werkzeug.exceptions import HTTPException
from werkzeug.routing import Map
from werkzeug.wrappers import Request

from nameko.constants import WEB_SERVER_CONFIG_KEY
from nameko.exceptions import ConfigurationError
from nameko.extensions import ProviderCollector, SharedExtension


try:
    STATE_IDLE = wsgi.STATE_IDLE
except AttributeError:  # pragma: no cover
    STATE_IDLE = None


BindAddress = namedtuple("BindAddress", ['address', 'port'])


def parse_address(address_string):
    address_re = re.compile(r'^((?P<address>[^:]+):)?(?P<port>\d+)$')
    match = address_re.match(address_string)
    if match is None:
        raise ConfigurationError(
            'Misconfigured bind address `{}`. '
            'Should be `[address:]port`'.format(address_string)
        )
    address = match.group('address') or ''
    port = int(match.group('port'))
    return BindAddress(address, port)


class HttpOnlyProtocol(HttpProtocol):
    # 与 `HttpProtocol.finish` 完全相同，但移除了 `greenio.shutdown_safe`。
    # 该函数仅在 SSL 套接字中需要，而我们不支持 SSL。这是一个权宜之计，直到 `此处 <https://bitbucket.org/eventlet/eventlet/pull-request/42`_ 或类似的功能被合并。
    def finish(self):
        try:
            # patched in depending on python version; confuses pylint
            # pylint: disable=E1101
            BaseHTTPServer.BaseHTTPRequestHandler.finish(self)
        except socket.error as e:
            # Broken pipe, connection reset by peer
            if get_errno(e) not in BROKEN_SOCK:
                raise
        self.connection.close()


class WebServer(ProviderCollector, SharedExtension):
    """一个 `SharedExtension`，用于包装 WSGI 接口以处理 HTTP 请求。

    `WebServer` 可以被子类化，通过重写 `get_wsgi_server` 和 `get_wsgi_app` 方法来添加额外的 WSGI 功能。
    """

    def __init__(self):
        super(WebServer, self).__init__()
        self._gt = None
        self._sock = None
        self._serv = None
        self._starting = False
        self._is_accepting = True

    @property
    def bind_addr(self):
        address_str = self.container.config.get(
            WEB_SERVER_CONFIG_KEY, '0.0.0.0:8000')
        return parse_address(address_str)

    def run(self):
        while self._is_accepting:
            sock, addr = self._sock.accept()
            sock.settimeout(self._serv.socket_timeout)
            self.container.spawn_managed_thread(
                partial(self.process_request, sock, addr)
            )

    def process_request(self, sock, address):
        try:
            if STATE_IDLE:  # pragma: no cover
                # eventlet >= 0.22
                # see https://github.com/eventlet/eventlet/issues/420
                self._serv.process_request([address, sock, STATE_IDLE])
            else:  # pragma: no cover
                self._serv.process_request((sock, address))

        except OSError as exc:
            # OSError("raw readinto() returned invalid length")
            # can be raised when a client disconnects very early as a result
            # of an eventlet bug: https://github.com/eventlet/eventlet/pull/353
            # See https://github.com/onefinestay/nameko/issues/368
            if "raw readinto() returned invalid length" in str(exc):
                return
            raise

    def start(self):
        if not self._starting:
            self._starting = True
            self._sock = eventlet.listen(self.bind_addr)
            # work around https://github.com/celery/kombu/issues/838
            self._sock.settimeout(None)
            self._serv = self.get_wsgi_server(self._sock, self.get_wsgi_app())
            self._gt = self.container.spawn_managed_thread(self.run)

    def get_wsgi_app(self):
        """获取用于处理请求的 WSGI 应用程序。

        此方法可以被重写，以应用 WSGI 中间件或完全替换 WSGI 应用程序。
        """
        return WsgiApp(self)

    def get_wsgi_server(
        self, sock, wsgi_app, protocol=HttpOnlyProtocol, debug=False
    ):
        """Get the WSGI server used to process requests."""
        return wsgi.Server(
            sock,
            sock.getsockname(),
            wsgi_app,
            protocol=protocol,
            debug=debug,
            log=getLogger(__name__)
        )

    def stop(self):
        self._is_accepting = False
        self._gt.kill()
        self._sock.close()
        super(WebServer, self).stop()

    def make_url_map(self):
        url_map = Map()
        for provider in self._providers:
            rule = provider.get_url_rule()
            rule.endpoint = provider
            url_map.add(rule)
        return url_map

    def context_data_from_headers(self, request):
        return {}


class WsgiApp(object):

    def __init__(self, server):
        self.server = server
        self.url_map = server.make_url_map()

    def __call__(self, environ, start_response):
        # 设置为浅模式，以便在未取消之前，任何人都无法读取请求数据。
        # 这使得在所有情况下，如果需要，可以将连接升级为双向 WebSocket 连接。
        # 常规请求处理代码会自动取消此标志。
        # 
        # 如果我们不这样做，某些代码可能会在此之前访问表单数据，
        # 这可能导致死锁，因为此时浏览器不再从我们的套接字读取数据。
        request = Request(environ, shallow=True)
        adapter = self.url_map.bind_to_environ(environ)
        try:
            provider, values = adapter.match()
            request.path_values = values
            rv = provider.handle_request(request)
        except HTTPException as exc:
            rv = exc
        return rv(environ, start_response)
