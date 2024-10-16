.. _benefits_of_dependency_injection:

依赖注入的好处
--------------------------------

Nameko 中的依赖注入模式促进了服务各个组件之间的关注点分离。这里存在一个自然的划分，"服务代码"——与服务的 :ref:`单一目的 <single_purpose>` 相关的应用逻辑——与服务操作所需的其余代码之间的区别。

假设你有一个缓存服务，负责从 memcached 中读取和写入数据，并包含一些特定业务的失效规则。这些失效规则显然是应用逻辑，而与 memcached 的复杂网络接口可以抽象为一个依赖。

分离这些关注点使得在孤立环境中测试服务代码变得更容易。这意味着在测试你的缓存服务时，你不需要有一个 memcached 集群。此外，指定来自 memcached 集群的模拟响应也很简单，以测试失效的边缘案例。

分离还可以防止测试范围相互渗透。如果缓存服务与其用于与 memcached 通信的机制之间没有明确的接口，便会倾向于将网络故障的边缘案例覆盖在缓存服务的测试套件中。实际上，这种情况的测试应该作为 memcached 依赖的测试套件的一部分。当依赖被多个服务使用时，这一点就变得更加明显——如果没有分离，你就必须重复网络故障测试，或者在测试覆盖范围中看起来存在漏洞。

在更大的团队中，一个更微妙的好处显现出来。依赖通常封装了应用程序中最棘手和最复杂的方面。服务代码是无状态和单线程的，而依赖必须处理并发和线程安全。这可以为初级开发者和高级开发者之间提供一种有益的劳动分工。

依赖将通用功能与定制的应用逻辑分离。它们可以被编写一次并由多个服务重复使用。Nameko 的 :ref:`社区扩展 <community_extensions>` 旨在促进团队之间的共享。
