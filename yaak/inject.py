# -*- coding: utf-8 -*-
# Copyright (c) 2010 Sylvain Prat. This program is open-source software,
# and may be redistributed under the terms of the MIT license. See the
# LICENSE.txt file in this distribution for details.

"""The `YAAK.inject`_ module implements dependency injection. See
`this article`_ from Martin Fowler for an explanation of dependency
injection and its usefulness when developing enterprise application.

.. _this article: http://martinfowler.com/articles/injection.html
.. _YAAK.inject: http://bitbucket.org/sprat/yaak.inject

Here is a tutorial that explains how to use this module.

First, import the ``yaak.inject`` module so that you can use the injection
functionality in your application:

  >>> from yaak import inject

Create a class whose instances have to be injected a *feature*
identified by the string ``IService`` (but could be any hashable type, such
as a class):

  >>> class Client(object):
  ...   service = inject.Attr('IService')  # inject a feature as an attribute
  ...   def use_service(self):
  ...     self.service.do_something()  # use the injected feature
  ...

Also, create a class (or any callable) that implements the *feature*:

  >>> class Service(object):
  ...   def do_something(self):
  ...     print "Service: I'm working hard"
  ...

Then, when you configure your application, you need to wire an implementation for
each *feature*. In this case, we provide an implementation for the
``IService`` feature:

  >>> inject.provide('IService', Service)

Note that we provide a factory (class) for the feature and not the instance
itself. You'll see later why.

Now, a Client instance can use the service:

  >>> client = Client()
  >>> client.use_service()
  Service: I'm working hard

When you use the default ``provide`` behavior, all instances of the Client
class will be injected the same Service instance:

  >>> another_client = Client()
  >>> client.service is another_client.service
  True

In fact, the default behavior when you ``provide`` a feature is to create a
thread-local singleton that is injected in all instances that request the
feature. That's what we call the *scope*: it defines the lifetime of the
feature instance.

You may want a different ``IService`` instance for each Client. You can do that
by changing the default scope to ``Transient`` when you provide the feature:

  >>> inject.provide('IService', Service, scope=inject.Scope.Transient)

Then, a different Service instance is injected in each new Client instance:

  >>> client = Client()
  >>> another_client = Client()
  >>> client.service is another_client.service
  False

You can also declare injected features as function/method parameters instead
of attributes:

  >>> class Client(object):
  ...   @inject.Param(service='IService')
  ...   def __init__(self, text, service):
  ...     self.text = text
  ...     self.service = service
  ...   def use_service(self):
  ...     print self.text
  ...     self.service.do_something()
  ...

Then you could use the Client class and get the parameters injected
automatically if you don't provide a value for them:
  
  >>> client = Client('This is a text')
  >>> client.use_service()
  This is a text
  Service: I'm working hard

That's the easiest way to declare injected parameters. But if you want to
keep your class decoupled from the injection framework, you can also define
the injection afterwards:
  
  >>> class Client(object):
  ...   def __init__(self, text, service):
  ...     self.text = text
  ...     self.service = service
  ...   def use_service(self):
  ...     print self.text
  ...     self.service.do_something()
  ...
  >>> inject_service = inject.Param(service='IService')
  >>> InjectedClient = inject_service(Client)
  >>> client = InjectedClient('This is a text')
  >>> client.use_service()
  This is a text
  Service: I'm working hard
"""

import collections
import functools
import inspect
import logging
import threading


__version__ = "0.1.0"


# logger that could help debug injection issues
log = logging.getLogger(__name__)


class Scope(object):
    """Enumeration of the different scope values. Not all scopes are available
    in all contexts."""
    # one instance per application (shared by threads)
    Application = 'Application'
    # one instance per thread - this is the default (secure)
    Thread = 'Thread'
    # a new instance is created each time the feature is injected
    Transient = 'Transient'
    # one instance per HTTP request
    Request = 'Request'
    # one instance per HTTP session
    Session = 'Session'


class UndefinedScopeError(Exception):
    """Exception raised when using a scope that has not been defined yet."""


class ScopeManager(threading.local):
    """Manages scope contexts where we store the instances to be used in
    injection."""

    def __init__(self):
        """Creates a new scope manager."""
        self._context = {}
        self._context[Scope.Thread] = {}
        self._context[Scope.Application] = _ApplicationContext

    def enter_scope(self, scope, context=None):
        self._context[scope] = context if context is not None else {}

    def exit_scope(self, scope):
        del self._context[scope]

    def context(self, scope):
        if scope != Scope.Transient:
            scope_context = self._context.get(scope)
        else:
            scope_context = {}

        if scope_context is None:
            raise UndefinedScopeError("No scope defined for " + scope)

        return scope_context


class ScopeContext(object):
    """Defines a scope for injection using a python context manager."""

    def __init__(self, scope, context=None, scope_manager=None):
        """Creates a scope context for the specified `scope`. If `context`
        is passed a dictionary, the created instances will be stored in
        this dictionary. Otherwise, a new dictionary will be created for
        storing instance each time we enter the scope. So the `context`
        argument can be used to recall a previous context. If `scope_manager`
        is specified, contexts will be stored in this `scope_manager`.
        Otherwise, the default scope manager will be used instead."""
        self.scope = scope
        self.context = context
        self.scope_manager = scope_manager or _DefaultScopeManager

    def __enter__(self):
        self.scope_manager.enter_scope(self.scope, self.context)
        return self

    def __exit__(self, type, value, traceback):
        self.scope_manager.exit_scope(self.scope)
        return False  # let the exception pass through


class MissingFeatureError(Exception):
    """Exception raised when no implementation has been provided for a
    feature."""


class FeatureProvider(object):
    """Provides features for injection when requested, create instances
    when necessary and use the scope manager to obtain the scoped context
    where we store the created instances."""

    def __init__(self, scope_manager=None):
        """Creates a feature provider. If `scope_manager` is specified,
        feature instances will be stored in the contexts given by the
        `scope_manager`. Otherwise, the default scope manager will be
        used instead."""
        self.scope_manager = scope_manager or _DefaultScopeManager
        self.clear()

    def clear(self):
        """Unregister all features"""
        self._feature_descriptors = {}

    def provide(self, feature, factory, scope=Scope.Thread):
        """Provide a factory that build (scoped) instances of the feature.

        Note that you can change the factory for a feature by providing the
        same feature again, but the injected instances that have a reference
        on the feature instance will not get a new instance."""
        self._feature_descriptors[feature] = (factory, scope)

    def get(self, feature):
        """Retrieve a (scoped) feature instance. Either find the instance in
        the associated context or create a new instance using the factory
        method and store it in the context."""
        feature_descriptor = self._feature_descriptors.get(feature)
        if feature_descriptor is None:
            raise MissingFeatureError("No feature provided for", feature)
        factory, scope = feature_descriptor
        scope_context = self.scope_manager.context(scope)
        instance = scope_context.get(feature)
        if instance is None:
            instance = factory()
            scope_context[feature] = instance
            log.debug('New instance ' + repr(instance) +
                      ' created in scope ' + scope +
                      ' for the feature ' + repr(feature))
        else:
            log.debug('Found ' + repr(instance) + ' in scope ' + scope +
                      ' for the feature ' + repr(feature))
        return instance

    __getitem__ = get  # for convenience


class Attr(object):
    """Descriptor that provides attribute-based dependency injection."""

    def __init__(self, feature, feature_provider=None):
        """Inject a `feature` (given as an identifier) in an instance
        attribute. If a `feature_provider` is specified, the feature instance
        will be retrieved from this provider. Otherwise, the default feature
        provider will be used instead."""
        self.feature = feature
        self.provider = feature_provider or _DefaultFeatureProvider
        self._name = None  # cache for the attribute name

    def _find_name(self, type):
        """Look for the name of the attribute that references this descriptor.
        """
        for cls in type.__mro__:  # support inheritance of injected classes
            for key, value in cls.__dict__.items():
                if value is self:
                    return key

    def __get__(self, obj, type=None):
        """Bind a feature instance to the object passed to the descriptor"""
        if obj is None:
            msg = 'Injection is not supported for class instances'
            raise AttributeError(msg)

        # get the feature instance to be bound to the object
        callable_provider = isinstance(self.provider, collections.Callable)
        provider = self.provider() if callable_provider else self.provider
        feature = provider.get(self.feature)

        # find the name of the attribute that references this descriptor
        if not self._name:
            self._name = self._find_name(type)

        # replace this descriptor by the bound feature instance
        setattr(obj, self._name, feature)
        log.debug('The feature ' + repr(feature) +
                  ' has been injected into the attribute ' +
                  repr(self._name) + ' of ' + repr(obj))

        return feature


class Param(object):
    """Decorator that provides parameter-based dependency injection."""

    def __init__(self, feature_provider=None, **injections):
        """Inject feature instances into function parameters. First, specify
        the parameters that should be injected a feature (given as an
        identifier) as keyword arguments (e.g. param='feature'). Then, each
        time the function will be called, the arguments will be passed new
        (scoped) feature instances. If a `feature_provider` is specified, the
        feature instances will be retrieved from this provider. Otherwise,
        the default feature provider will be used instead."""
        self.injections = injections
        self.provider = feature_provider or _DefaultFeatureProvider

    def __call__(self, wrapped):
        if inspect.isclass(wrapped):
            # support class injection by injecting the __init__ method
            wrapped.__init__ = self.wrap(wrapped.__init__)
            return wrapped
        else:
            return self.wrap(wrapped)

    def _retrieve_feature(self, feature, provider, message):
        feature = provider.get(feature)
        log.debug(message)
        return feature

    def wrap(self, func):
        """Wrap a function so that one parameter is automatically injected
        and the other parameters should be passed to the wrapper function in
        the same order as in the wrapped function, or by keyword arguments"""
        # deal with stacked decorators: find the original function and the
        # injected parameters
        injected_params = getattr(func, 'injected_params', {})
        injected_function = getattr(func, 'injected_function', func)

        # add the new injected parameter
        callable_provider = isinstance(self.provider, collections.Callable)
        provider = self.provider() if callable_provider else self.provider
        for param, feature in self.injections.items():
            message = ('The feature ' + repr(feature) +
                       ' has been injected into the parameter ' +
                       repr(param) + ' of ' + repr(injected_function))
            resolver = BindingResolver(lambda feature=feature, message=message:
                self._retrieve_feature(feature, provider, message))
            injected_params[param] = resolver

        # inject it (functools.partial is not suitable here)
        new_func = bind(injected_function, **injected_params)
        new_func.injected_params = injected_params
        new_func.injected_function = injected_function
        functools.update_wrapper(new_func, injected_function)

        return new_func


class BindingNotSupportedError(Exception):
    """Exception raised when a function could not be used in the bind method"""


def bind(func, **frozen_args):
    """This function is similar to the functools.partial function: it
    implements partial application. That is, it's a way to transform a function
    to another function with less arguments, because some of the arguments of
    the original function will get some fixed values: these arguments are
    called frozen arguments. Unlike the functools.partial function, frozen
    parameters can be anywhere in the signature of the transformed function,
    they are not required to be the first or last ones. Also, you can pass a
    BindingResolver instance as the value of a parameter to get the value from
    a resolve function (e.g. to implement late binding).

    Say you have a function `add` defined like this:
    >>> def add(a, b):
    ...   return a + b

    You can bind the parameter `b` to the value `1`:
    >>> add_one = bind(add, b=1)

    Now, `add_one` has only one parameters `a` since `b` will always get the
    value `1`. So:
    >>> add_one(1)
    2
    >>> add_one(2)
    3
    """
    # special case for methods (bound or unbound)
    self = getattr(func, 'im_self', None)
    func = getattr(func, 'im_func', func)

    # get signature information
    argspec = inspect.getargspec(func)

    # variable arguments list is not supported
    if argspec.varargs is not None:
        msg = 'Could not bind a function with a variable arguments list'
        raise BindingNotSupportedError(msg)

    def inner_func(*inner_args, **inner_kwargs):
        # call the value if it is an instance of BindingResolver: this
        # implements late binding
        def resolve(value):
            return value() if isinstance(value, BindingResolver) else value

        arg_dict = dict((arg, resolve(value))
                        for arg, value in frozen_args.items())

        # special case for bound methods: add self to the keyword arguments
        if self:
            arg_dict['self'] = self

        arg_idx = 0
        for arg in argspec.args:
            # bound argument?
            if arg in arg_dict:
                continue

            # are we finished with positional inner arguments?
            if arg_idx >= len(inner_args):
                break

            # check that the positional argument is not also passed in
            # keyword arguments?
            if arg in inner_kwargs:
                msg = func.__name__ + "() got multiple values" + \
                    " for keyword argument '" + arg + "'"
                raise TypeError(msg)

            # OK, use the next positional argument
            arg_dict[arg] = inner_args[arg_idx]
            arg_idx += 1

        # call the bound function with the extended arguments list
        arg_dict.update(inner_kwargs)
        return func(**arg_dict)

    return inner_func


class BindingResolver(object):
    def __init__(self, func):
        self._func = func

    def __call__(self):
        return self._func()


class WSGIRequestScope(object):
    """WSGI middleware that provides the 'Request' scope for the
    wrapped application."""

    def __init__(self, app, scope_manager=None):
        self.app = app
        self.scope_manager = scope_manager

    def __call__(self, environ, start_response):
        """Provide a 'Request' scope for each request."""
        with ScopeContext(scope=Scope.Request,
                          scope_manager=self.scope_manager):
            # We iterate over the results to force the application to
            # generate its results. Otherwise, we may unregister the context
            # before the application really use it.
            for item in self.app(environ, start_response):
                yield item


# module constants
_ApplicationContext = {}
_DefaultScopeManager = ScopeManager()
_DefaultFeatureProvider = FeatureProvider()
provide = _DefaultFeatureProvider.provide
get = _DefaultFeatureProvider.get
clear = _DefaultFeatureProvider.clear
