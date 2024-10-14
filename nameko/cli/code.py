from __future__ import absolute_import

from code import InteractiveConsole


# 该类由在子进程中运行的测试覆盖，因此不包含在覆盖范围内 (`no cover`)。
class RaisingInteractiveConsole(InteractiveConsole):  # pragma: no cover
    """ Custom InterativeConsole class that allows raising exception if needed.
    """

    def __init__(
        self, locals=None, filename="<console>", raise_expections=False
    ):
        InteractiveConsole.__init__(self, locals=locals, filename=filename)
        self.raise_expections = raise_expections

    def runcode(self, code):
        try:
            exec(code, self.locals)
        except SystemExit:
            raise
        except:
            self.showtraceback()
            if self.raise_expections:
                raise


# 该函数由在子进程中运行的测试覆盖，因此不包含在覆盖范围内 (`no cover`)。
def interact(
    banner=None, local=None, raise_expections=False
):  # pragma: no cover
    try:
        import readline  # noqa: F401
    except ImportError:
        pass

    console = RaisingInteractiveConsole(
        locals=local, raise_expections=raise_expections
    )
    console.interact(banner=banner)
