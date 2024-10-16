种示例
================


rpc 调用
------------------

.. literalinclude:: rpc.py


异步 rpc 调用
------------------

.. literalinclude:: async_rpc.py

本质就是不等待消费线程返回，再次调用远程方法, 见 :meth:`~nameko.rpc.MethodProxy.call_async`

.. _travis:

Travis Web 服务
------------------

.. literalinclude:: travis.py

Event
--------

.. literalinclude:: events.py

Event broadcast
^^^^^^^^^^^^^^^^

.. literalinclude:: event_broadcast.py

Timer
--------

.. literalinclude:: timer.py


standalone RPC
----------------

.. literalinclude:: standalone_rpc.py


standalone events
----------------

.. literalinclude:: standalone_events.py


Service 
----------

Runner
^^^^^^^^^^

.. literalinclude:: service_runner.py

Container
^^^^^^^^^^

.. literalinclude:: service_container.py


http 
----------

.. literalinclude:: http.py

exceptions
^^^^^^^^^^

.. literalinclude:: http_exceptions.py

advanced
^^^^^^^^^^

.. literalinclude:: advanced_http.py


自定义 receive
----------------

sqs receive
^^^^^^^^^^^^

.. literalinclude:: sqs_receive.py

sqs service
^^^^^^^^^^^^

.. literalinclude:: sqs_receive.py

sqs send
^^^^^^^^^^^^

.. literalinclude:: sqs_receive.py