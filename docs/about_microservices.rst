关于微服务
===================

    一种将软件设计为一组小服务的方法，每个服务在其自己的进程中运行，并通过轻量级机制进行通信。

    -- Martin Fowler, `微服务架构 <http://martinfowler.com/articles/microservices.html>`_

微服务通常是与“单体”进行对比来描述的——单体是一个作为单个单元构建的应用程序，对其任何部分的更改都需要构建和部署整个应用程序。

而在微服务中，功能被拆分成具有明确定义边界的“服务”。每个服务可以单独开发和部署。

使用微服务有许多好处和缺点，这些在马丁·福勒的 `论文 <http://martinfowler.com/articles/microservices.html>`_ 中被详细解释。并不是所有这些优缺点都总是适用，因此下面我们将概述一些与 Nameko 相关的内容。

好处
--------

.. _single_purpose:

* 小而专一

  将大型应用程序拆分为较小的松耦合模块减少了开发者的认知负担。专注于一个服务的开发者无需理解其余应用程序的内部细节；他们可以依赖其他服务的高层接口。

  在单体应用中更难实现这一点，因为“模块”之间的边界和接口更模糊。

* 明确的 `发布接口 <http://martinfowler.com/bliki/PublishedInterface.html>`_

  Nameko 服务的入口点明确声明其发布接口。这是服务与调用者之间的边界，因此必须考虑或维护向后兼容性。

* 可单独部署

  与只能一次性发布的单体应用不同，Nameko 服务可以单独部署。对一个服务的更改可以在不影响其他服务的情况下进行和推出。长时间运行和深思熟虑的发布周期可以分解为更小、更快速的迭代。

* 专业化

  解耦的应用模块可以自由使用专业的库和依赖项。在单体应用中，可能被迫选择一种通用库，而微服务不受其他应用选择的限制。


缺点
---------

* 开销

  RPC 调用的开销高于进程内方法调用。进程将花费大量时间等待 I/O。虽然 Nameko 通过并发和 eventlet 减少 CPU 周期的浪费，但每次调用的延迟仍然比单体应用长。

* 跨服务事务

  在多个进程之间分配事务困难得几乎没有意义。微服务架构通过改变它们暴露的 API（见下文）或仅提供最终一致性来解决此问题。

* 粗粒度 API

  服务调用之间的开销和缺乏事务性鼓励使用较粗的 API。跨越服务边界的成本高且非原子。

  在单体应用中，你可能会编写代码进行多次调用以实现特定目标，而微服务架构则会鼓励你编写更少、但更重的调用，以确保原子性或最小化开销。

* 理解相互依赖

  将应用程序拆分为多个独立组件需要理解这些组件如何相互作用。当组件位于不同的代码库（和开发者思维空间）中时，这一点尤其困难。

  未来，我们希望在 Nameko 中提供工具，使理解、记录和可视化服务间依赖关系变得更加容易。

进一步说明
-------------

微服务可以逐步采纳。构建微服务架构的一个好方法是先从单体应用中提取适当的逻辑块，然后将其转化为独立的服务。
