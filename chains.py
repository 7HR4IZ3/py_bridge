
class JSchain:
    '''
    JSchain keeps track of the dynamically generated Javascript. It
    tracks names, data item accesses and function calls. JSchain
    is usually not used directly, but accessed through the JS class.

    Attributes
    -----------
    state
        A JSstate instance. This instance should be the same
        for all call of the same session.

    Notes
    -----------
    There is a special name called `dom` which is shorthand for
    lookups. For example,

        js.dom.button1.innerHTML

    Becomes

        js.document.getElementById("button1").innerHTML

    Example
    --------------
    ```
    state = JSstate(server)
    js = JSchain(state)
    js.document.getElementById("txt").value
    ```
    '''

    def __init__(self, state=None):
        self.state: ClientContext = state
        self.chain = []
        self.keep = True
    
    def _bind(self, state):
        self.state = state

    def _dup(self):
        '''
        Duplicate this chain for processing.
        '''
        js = JSchain(self.state)
        js.chain = self.chain.copy()  # [x[:] for x in self.chain]
        return js

    def _add(self, attr, prepend="."):
        '''
        Add item to the chain. If `dot` is True, then a dot is added. If
        not, this is probably a function call and not dot should be added.
        '''
        if not attr:
            # this happens when __setattr__ is called when the first
            # item of a JSchain is an assignment
            return self
        if prepend and len(self.chain) > 0:
            self.chain.append(prepend)
        
        self.chain.append(attr)
        return self

    def _prepend(self, attr):
        '''
        Add item to the start of the chain. 
        '''

        self.chain.insert(0, attr)
        return self

    def _last(self):
        '''
        Last item on the chain.
        '''
        return self.chain[-1]
    
    def new(self, *args, **kwargs):
        self._prepend(" ")
        self._prepend("new")
        all_args = list(args) +  list(kwargs.values())

        self._add('(', prepend="")
        [self._add(x, prepend="") for x in self._formatArgs(all_args)]
        if self._last() == ",":
            self.chain.pop()
        self._add(')', prepend="")
        return self.eval()
    
    def js(self, code, eval=False):
        self._add(code, prepend="")
        if eval:
           return self.eval()
        return self

    def __getattr__(self, attr):
        '''
        Called to process items in a dot chain in Python syntax. For example,
        in a.b.c, this will get called for "b" and "c".
        '''
        # __iter__ calls should be ignored
        if attr == "__iter__":
            return self
        return self.getdata(attr)

    def getdata(self, attr, aprepend="."):
        if self._last() == 'dom':
            # substitute the `dom` shortcut
            self.chain[-1] = 'document'
            self._add('getElementById')
            self._add('("{}")'.format(attr), prepend="")
        else:
            # add the item to the chain
            self._add(attr, prepend=aprepend)
        return self

    def __setattr__(self, attr, value):
        value = JSroot._v(value)
        if attr == "chain" or attr == "state" or attr == "keep":
            # ignore our own attributes. If an attribute is added to "self" it
            # should be added here. I suppose this could be evaluated dynamically
            # using the __dict__ member.
            super(JSchain, self).__setattr__(attr, value)
            return value
        # print("SET", attr, value)
        self.setdata(attr, value)
        self.execExpression()

    def setdata(self, attr, value, aprepend="."):
        '''
        Called during assigment, as in `self.js.x = 10` or during a call
        assignement as in `self.js.onclick = func`, where func is a function.
        '''
        # if callable(value):
        #     # is this a function call?
        #     idx = self.state.proxy_object(value)
        #     self._add("eval::"+attr, prepend=aprepend)
        #     # self._add("=function(){{server._callfxn(%s);}}" % idx, prepend="")
        #     self._add(" = client.formatters.callable_proxy('', client.parse(`%s`));" % idx, prepend="")
        # else:
        # otherwise, regular assignment
        self._add(attr, prepend=aprepend)
        self._add("=", prepend="")
        [self._add(x, prepend="") for x in self._formatArg(value)]

        # print(self.chain)
        return value

    def __setitem__(self, key, value):
        jkey = "['%s']" % str(key)
        self.setdata(jkey, value, aprepend="")
        self.execExpression()
        return value

    def __getitem__(self, key):
        # all keys are strings in json, so format it
        key = str(key)
        c = self._dup()
        c._prepend("'%s' in " % key)
        haskey = c.eval()
        if not haskey:
            raise KeyError(key)
        jkey = "['%s']" % key
        c = self.getdata(jkey, aprepend="")
        return c.eval()
    
    # def _formatArg(self, arg):
    #     arg = JSroot._v(arg)

    #     # print(arg, type(arg))
    #     # print()
    #     if isinstance(arg, JsObject):
    #         self._add(arg.code, prepend="")
    #     elif isinstance(arg, JsProxy):
    #         self._add(f"client.getProxyObject('{arg.__data__['key']}')", prepend="")
    #     elif isinstance(arg, JsClass):
    #         item = self.state.proxy_object(arg)
    #         return self._add("client.PyProxy("+item+")", prepend="")
    #     elif isinstance(arg, list):
    #         self._add("[", prepend="")
    #         self._formatArgs(arg)
    #         self._add("]", prepend="")
    #     elif isinstance(arg, tuple):
    #         self._add("(", prepend="")
    #         self._formatArgs(arg)
    #         self._add(")", prepend="")
    #     elif isinstance(arg, set):
    #         self._add("{", prepend="")
    #         self._formatArgs(arg)
    #         self._add("}", prepend="")
    #     elif isinstance(arg, dict):
    #         self._add("{", prepend="")
    #         for k,v in arg.items():
    #             self._add(self._formatArg(k), prepend="")
    #             self._add(":", prepend="")
    #             self._add(self._formatArg(v), prepend="")
    #             self._add(",", prepend="")
    #         if self._last() == ",":
    #             self.chain.pop()
    #         self._add("}", prepend="")
    #     elif hasattr(arg, "to_js"):
    #         arg.to_js(self, arg)
    #         # self._add(f'{val}', prepend="")
    #     elif callable(arg):
    #         temp_name = getattr(arg, "__name__", f"temp_func_{random.randint(0, 100000000)}")

    #         if not hasattr(self.state.obj, temp_name):
    #             self.state.obj.__register__(temp_name, arg)
    #             # print(temp_name, self.state.obj.customs)

    #         self._add(f"(...args) => server.{temp_name}.then(f => f(...args))", prepend="")
    #     else:
    #         val = repr(arg)
    #         self._add(f'{val}', prepend="")

    def _formatArg(self, arg):
        # arg = JSroot._v(arg)

        ret = []

        # print(arg, type(arg))
        # print()
        if isinstance(arg, JsObject):
            ret.append(arg.code)
        elif isinstance(arg, JSchain):
            ret.append(arg._statement())
        elif isinstance(arg, JsProxy):
            ret.append(f"client.getProxyObject('{arg.__data__['key']}')")
        elif isinstance(arg, JsClass):
            item = self.state.proxy_object(arg)
            ret.append("client.get_result("+item+")")
        elif isinstance(arg, list):
            ret.append("[")
            [ret.append(x) for x in self._formatArgs(arg)]
            ret.append("]")
        elif isinstance(arg, tuple):
            ret.append("(")
            [ret.append(x) for x in self._formatArgs(arg)]
            ret.append(")")
        elif isinstance(arg, set):
            ret.append("{")
            [ret.append(x) for x in self._formatArgs(arg)]
            ret.append("}")
        elif isinstance(arg, dict):
            ret.append("{")
            for k,v in arg.items():
                [ret.append(x) for x in self._formatArg(k)]
                ret.append(":")
                [ret.append(x) for x in self._formatArg(v)]
                ret.append(",")
            if len(ret) > 1 and ret[-1] == ",":
                ret.pop()
            ret.append("}")
        elif hasattr(arg, "to_js"):
            [ret.append(x) for x in arg.to_js(self, arg)]
            # ret.append(f'{val}')
        elif isinstance(arg, NoneType):
            ret.append("null")
        # elif isinstance(arg, (FunctionType, MethodType)):
        #     pass
        else:
            if not isinstance(arg, (int, str, dict, set, tuple, bool, float)):
                item = self.state.proxy_object(arg)
                ret.append("client.get_result("+item+")")
            else:
                # try:
                #     val = json.dumps(arg)
                # except:
                val = repr(arg)
                ret.append(f'{val}')
        # elif callable(arg):
        #     temp_name = getattr(arg, "__name__", f"temp_func_{random.randint(0, 100000000)}")

        #     if not hasattr(self.state.obj, temp_name):
        #         self.state.obj.__register__(temp_name, arg)
        #         # print(temp_name, self.state.obj.customs)

        #     ret.append(f"server.{temp_name}")
        # else:
        #     val = repr(arg)
        #     ret.append(f'{val}')
        return ret

    def _formatArgs(self, args):
        ret = []

        for item in args[:-1]:
            [ret.append(x) for x in self._formatArg(item)]
            ret.append(",")
            # self._add(",", prepend="")

        if len(args) > 0:
            [ret.append(x) for x in self._formatArg(args[-1])]
        return ret

            # self._formatArg(args[-1])

    # def __call__(self, *args, **kwargs):
    #     '''
    #     Called when we are using in a functiion context, as in
    #     `self.js.func(15)`.
    #     '''
    #     # evaluate the arguments
    #     p1 = [self.toJson(req, JSroot._v(v)) for v in args]
    #     p2 = [self.toJson(req, JSroot._v(v)) for k, v in kwargs.items()]
    #     s = ','.join(p1 + p2)
    #     # create the function call
    #     self._add('('+s+')', prepend="")
    #     return self
    def __call__(self, *args, **kwargs):
        '''
        Called when we are using in a functiion context, as in
        `self.js.func(15)`.
        '''
        # evaluate the arguments
        # p1 = [self.toJson(req, JSroot._v(v)) for v in args]
        # p2 = [self.toJson(req, JSroot._v(v)) for k, v in kwargs.items()]
        all_args = list(args) +  list(kwargs.values())

        # print(all_args)

        self._add('(', prepend="")

        [self._add(x, prepend="") for x in self._formatArgs(all_args)]

        if self._last() == ",":
            self.chain.pop()
        self._add(')', prepend="")
        # print(self.chain)
        return self

    def _statement(self):
        '''
        Join all the elements and return a string representation of the
        Javascript expression.
        '''
        return ''.join(self.chain)

    def __bytes__(self):
        '''
        Join the elements and return as bytes encode in utf8 suitable for
        sending back to the browser.
        '''
        return (''.join(self.chain)).encode("utf8")

    def evalAsync(self):
        if self.keep:
            stmt = self._statement()
            self.state.addTask(stmt)
            # mark it as evaluated
            self.keep = False

    def __del__(self):
        '''
        Execute the statment when the object is deleted.

        An object is deleted when it goes out of scope. That's when it is put
        together and sent to the browser for execution. 

        For statements,
        this happens when the statement ends. For example,

           self.js.func(1)

        goes out of scope when the statement after func(1). However,

           v = self.js.myvalue

        goes out of scope when the "v" goes out of scope, usually at then end of
        the function where it was used. In this case, the Javascript will be
        evaluated when "v" itself is evaluated. This happens when you perform
        an operation such as "v+5", saving or printing.

        "v" in the example above is assigned an object and not a value. This
        means that every time it is evaluated in an expression, it goes back 
        to the server and retrieves the current value.

        On the other hand,

           self.v = self.js.myvalue

        will probably never go out of scope because it is tied to the class.
        To force an evaluation, call the "eval()"
        method, as in "self.js.myvalue.eval()".
        '''
        if not self.keep: return
        # print("!!!DEL!!!")
        try:
            if self.state:
                self.execExpression()
        except Exception as ex:
            if self.state:
                self.state._error = ex
                self.state.log_error("Uncatchable exception: %s", str(ex))
            raise ex

    def execExpression(self):
        # Is this a temporary expression that cannot evaluated?
        if self.keep:
            stmt = self._statement()
            # print("EXEC", stmt)
            if self.state.singleThread:
                # print("ASYNC0", stmt)
                # can't run multiple queries, so just run it async
                self.state.addTask(stmt)
            else:
                # otherwise, wait for evaluation
                # print("SYNC", stmt)
                try:
                    self.eval()
                finally:
                    self.keep = False

            # mark it as evaluated
            self.keep = False

    def eval(self, timeout=10):
        '''
        Evaluate this object by converting it to Javascript, sending it to the browser
        and waiting for a response. This function is automatically called when the object
        is used in operators or goes out of scope so it rarely needs to
        be called directly.

        However, it is helpful
        to occasionally call this to avoid out-of-order results. For example,

            v = self.js.var1
            self.js.var1 = 10
            print(v)

        This will print the value 10, regardless of what var1 was before the assignment.
        That is because "v" is the abstract statemnt, not the evaluated value. 
        The assigment "var1=10" is evaluated immediately. However,
        "v" is evaluated by the Browser 
        when "v" is converted to a string in the print statement. If this is a problem,
        the code should be changed to:

            v = self.js.var1.eval()
            self.js.var1 = 10
            print(v)

        In that case, "v" is resolved immediately and hold the value of var1 before the
        assignment.

        Attributes
        -------------
        timeout
            Time to wait in seconds before giving up if no response is received.
        '''
        if not self.keep:
            return 0
            # raise ValueError("Expression cannot be evaluated")
        else:
            self.keep = False

        stmt = self._statement()
        # print("EVAL", stmt)

        c = self.state

        # if not c.lock.acquire(blocking = False):
        #     c.log_error("App is active so you cannot wait for result of JS: %s" % stmt)
        #     c.addTask(stmt)
        #     return 0
        #     # raise RuntimeError("App is active so you cannot evaluate JS for: %s" % stmt)

        try:
            # idx, q = c.addQuery()
            data = c.toJson(None, stmt)
            cmd = 'client.sendFromBrowserToServer(%s)'%(data)
            socket = c.socket or c.socketio
            value = {
                "msg": None
            }

            if socket:
                socket.send(c.toJson(None, {"expression": cmd}))
            elif c.socketio:
                socket.emit("message", c.toJson(None, {"expression": cmd}))

                on_msg = socket.handlers["/"].get("message")
                
                @socket.on("message")
                def _(ev, data):
                    print(data)
                    value["msg"] = data
                    socket.on("message")(on_msg)

            # else:
                # c.addTask(cmd)
            try:
                c.log_message("WAITING ON RESULT QUEUE")

                if c.socket:
                    try:
                        recv  = socket.receive()
                        result = json.loads(recv, cls=c.decoder)
                    except Exception as e:
                        raise e
                elif c.socketio:
                    try:
                        while True:
                            time.sleep(0.1)
                            if value["msg"]:
                                break
                        result = json.loads(value["msg"], cls=c.decoder)
                    except Exception as e:
                        raise e
                else:
                    result = {}
                # else:
                #     result = q.get(timeout=timeout)
                # print("Result is", result)
                c.log_message("RESULT QUEUE %s", result)
                # c.delQuery(idx)
            except Exception as e:
                raise e
                raise RuntimeError("Socker Error executing: ", cmd)
            except queue.Empty:
                c.log_message("TIMEOUT waiting on: %s", stmt)
                raise TimeoutError("Timout waiting on: %s" % stmt)

            if result.get("error", "") != "":
                c.log_error("ERROR EVAL %s : %s", result["error"], stmt)
                raise JsRuntimeError(result["error"] + ": " + stmt)
            
            if "value" in result:
                return result["value"]
            else:
                return 0

        finally:
            pass
            # c.lock.release()

    #
    # Magic methods. We create these methods for force the
    # Javascript to be evaluated if it is used in any
    # opreation.
    #
    def __cmp__(self, other): return self.eval().__cmp__(other)
    def __eq__(self, other): return self.eval().__eq__(other)
    def __ne__(self, other): return self.eval().__ne__(other)
    def __gt__(self, other): return self.eval().__gt__(other)
    def __lt__(self, other): return self.eval().__lt__(other)
    def __ge__(self, other): return self.eval().__ge__(other)
    def __le__(self, other): return self.eval().__le__(other)

    def __pos__(self): return self.eval().__pos__()
    def __neg__(self): return self.eval().__neg__()
    def __abs__(self): return self.eval().__abs__()
    def __invert__(self): return self.eval().__invert__()
    def __round__(self, n): return self.eval().__round__(n)
    def __floor__(self): return self.eval().__floor__()
    def __ceil__(self): return self.eval().__ceil__()
    def __trunc__(self): return self.eval().__trunc__()

    def __add__(self, other): return self.eval().__add__(other)
    def __and__(self, other): return self.eval().__and__(other)
    def __div__(self, other): return self.eval().__div__(other)
    def __divmod__(self, other): return self.eval().__divmod__(other)
    def __floordiv__(self, other): return self.eval().__floordiv__(other)
    def __lshift__(self, other): return self.eval().__lshift__(other)
    def __mod__(self, other): return self.eval().__mod__(other)
    def __mul__(self, other): return self.eval().__mul__(other)
    def __or__(self, other): return self.eval().__or__(other)
    def __pow__(self, other): return self.eval().__pow__(other)
    def __rshift__(self, other): return self.eval().__rshift__(other)
    def __sub__(self, other): return self.eval().__sub__(other)
    def __truediv__(self, other): return self.eval().__truediv__(other)
    def __xor__(self, other): return self.eval().__xor__(other)

    def __radd__(self, other): return self.eval().__radd__(other)
    def __rand__(self, other): return self.eval().__rand__(other)
    def __rdiv__(self, other): return self.eval().__rdiv__(other)
    def __rdivmod__(self, other): return self.eval().__rdivmod__(other)
    def __rfloordiv__(self, other): return self.eval().__rfloordiv__(other)
    def __rlshift__(self, other): return self.eval().__rlshift__(other)
    def __rmod__(self, other): return self.eval().__rmod__(other)
    def __rmul__(self, other): return self.eval().__rmul__(other)
    def __ror__(self, other): return self.eval().__ror__(other)
    def __rpow__(self, other): return self.eval().__rpow__(other)
    def __rrshift__(self, other): return self.eval().__rrshift__(other)
    def __rsub__(self, other): return self.eval().__rsub__(other)
    def __rtruediv__(self, other): return self.eval().__rtruediv__(other)
    def __rxor__(self, other): return self.eval().__rxor__(other)

    def __coerce__(self, other): return self.eval().__coerce__(other)
    def __complex__(self): return self.eval().__complex__()
    def __float__(self): return self.eval().__float__()
    def __hex__(self): return self.eval().__hex__()
    def __index__(self): return self.eval().__index__()
    def __int__(self): return self.eval().__int__()
    def __long__(self): return self.eval().__long__()
    def __oct__(self): return self.eval().__oct__()
    def __str__(self): return self.eval().__str__()
    def __dir__(self): return self.eval().__dir__()
    def __format__(self, formatstr): return self.eval().__format__(formatstr)
    def __hash__(self): return self.eval().__hash__()
    def __nonzero__(self): return self.eval().__nonzero__()
    def __repr__(self): return self.eval().__repr__()
    def __sizeof__(self): return self.eval().__sizeof__()
    def __unicode__(self): return self.eval().__unicode__()

    def __iter__(self): return self.eval().__iter__()
    def __reversed__(self): return self.eval().__reversed__()
    def __contains__(self, item): 
        d = self.eval()
        if isinstance(d, dict):
            # json makes all keys strings
            return d.__contains__(str(item))
        else:
            return d.__contains__(item)
    # def __missing__(self, key): return self.eval().__missing__(key)
