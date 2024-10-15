import nox


@nox.session
def docs(session):
    """nox -s docs -- serve"""
    session.install(".")
    session.install(
        "sphinx", "sphinx-autobuild", "sphinx-autoapi", "sphinxcontrib-spelling", "furo"
    )
    session.run("rm", "-rf", "build/html", external=True)
    sphinx_args = ["-W", "docs", "build/html"]

    if "serve" in session.posargs:
        session.run("sphinx-autobuild", *sphinx_args)
    else:
        session.run("sphinx-build", *sphinx_args)


@nox.session
def shell(session):
    """nox -s shell"""
    # 安装你需要的依赖（可选）
    session.install(".")
    # session.install(
    #     "sphinx", "sphinx-autobuild", "sphinx-autoapi", "sphinxcontrib-spelling", "furo"
    # )
    # session.run("rm", "-rf", "build/html", external=True)

    # 启动 shell
    session.run("zsh", external=True)  # 如果使用 zsh
