import os
# import json
# # from weakref import WeakKeyDictionary

# from .utils import generate_random_id
# from .proxy import BaseBridgeProxy

UNDEFINED = object()


class BridgeChain:
    def __init__(self):
        pass


class BaseBridgeConnection:

    def __init__(self, bridge, transporter, mode="auto_eval", server=None):
        self.__transporter = transporter
        self.__bridge = bridge
        self.__mode = mode
        self.__server__ = server

    def __getattr__(self, name):
        if self.__mode == "auto_eval":
            return self.__server__.recieve(action="evaluate", value=name)
        else:
            return BridgeChain(self)

    def __quit(self):
        self.__server__.stop()
        # pass

    def __del__(self):
        self.__quit()

    def __enter__(self, *a, **kw):
        return self

    def __exit__(self, *a, **kw):
        self.__quit()
        return


class NodeBridgeConnection(BaseBridgeConnection):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.__require = None

    def __getattr__(self, name):
        if name == "let" or name == "var":
            return self.__handle_let
        if name == "await_":
            return self.__handle_await
        if name == "_require": name = "require"
        return super().__getattr__(name)

    def __handle_let(self, *keys, **values):
        target = []

        [target.append(f"{key}") for key in keys]

        if values:
            for key in values:
                target.append(f"globalThis.{key} = {values[key]}")

        self.__getattr__(
            name=f"{', '.join(target)};"
        )

    def __handle_await(self, item):
        return self.__server__.recieve(
            action="await_proxy",
            location=item.__data__['location']
        )

    def require(self, module):
        if not self.__require:
            self.__require = self.__server__.recieve(
                action="evaluate", value='require'
            )
        return self.__require(
            os.path.join(os.getcwd(), module) if "." in module
            else module
        )


class BrowserBridgeConnection(NodeBridgeConnection):
    pass


class RubyBridgeConnection(BaseBridgeConnection):
    pass


class JavaBridgeConnection(BaseBridgeConnection):
    pass


class CSharpBridgeConnection(BaseBridgeConnection):
    pass


class GoLangBridgeConnection(BaseBridgeConnection):
    pass
