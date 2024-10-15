"""Nameko 内置依赖"""

from nameko.extensions import DependencyProvider


class Config(DependencyProvider):
    """依赖提供者，用于访问配置值。"""

    def get_dependency(self, worker_ctx):
        return self.container.config.copy()
