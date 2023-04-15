
class BaseBridgeProxy:
    def __init__(self, server, data):
        self.__server__ = server
        self.__data__ = data

    @property
    def _(self):
        return self.__cast__()

    def __cast__(self, target=(lambda a: a)):
        return target(self.__server__.recieve(
            action="get_primitive",
            location=self.__data__['location']
        ))

    def __dir__(self):
        return self.__server__.recieve(
            action="get_proxy_attributes",
            location=self.__data__['location']
        )

    def __call__(self, *args, **kwargs):
        return self.__server__.recieve(
            action="call_proxy",
            location=self.__data__['location'],
            args=args,
            kwargs=kwargs
        )

    def __getattr__(self, name):
        return self.__server__.recieve(
            action="get_proxy_attribute",
            location=self.__data__['location'],
            target=name
        )

    def __getitem__(self, index):
        return self.__server__.recieve(
            action="get_proxy_index",
            location=self.__data__['location'],
            target=index
        )

    def __setattr__(self, name, value):
        if name in ['__server__', '__data__']:
            return super().__setattr__(name, value)
        return self.__server__.recieve(
            action="set_proxy_attribute",
            location=self.__data__['location'],
            target=name,
            value=value
        )

    def __setitem__(self, index, value):
        return self.__server__.recieve(
            action="set_proxy_index",
            location=self.__data__['location'],
            target=index,
            value=value
        )

    def __str__(self):
        return self.__cast__(str)

    # def __del__(self):
    #     try:
    #         return self.__server__.recieve(
    #             action="delete_proxy",
    #             location=self.__data__['location']
    #         )
    #     except Exception:
    #         pass

    # def __bool__(self):
    #     return self.__cast__(bool)

    # def __int__(self):
    #     return self.__cast__(int)

    # def __len__(self):
    #     length = self.length
    #     if length is not None:
    #         return length.__cast__()
    #     return 0


class NodeBridgeProxy(BaseBridgeProxy):
    def __getattr__(self, name):
        if name == "new":
            return self.__new_constructor
        return super().__getattr__(name)

    def __new_constructor(self, *args, **kwargs):
        return self.__server__.recieve(
            action="call_proxy_constructor",
            location=self.__data__['location'],
            args=args,
            kwargs=kwargs
        )


class RubyBridgeProxy(BaseBridgeProxy):
    pass


class JavaBridgeProxy(BaseBridgeProxy):
    pass


class CSharpBridgeProxy(BaseBridgeProxy):
    pass


class GoLangBridgeProxy(BaseBridgeProxy):
    pass
