# -*- coding: utf-8 -*-
# Copyright (c) 2011 Sylvain Prat. This program is open-source software,
# and may be redistributed under the terms of the MIT license. See the
# LICENSE.txt file in this distribution for details.

"""The :mod:`yaak.inject` module implements dependency injection. Here is a
tutorial that explains how to use this module.

First, import the :mod:`yaak.inject` module so that you can use the injection
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

Then, when you configure your application, you need to wire an implementation
for each *feature*. In this case, we provide an implementation for the
``IService`` feature:

  >>> inject.provide('IService', Service)

Note that we provide a factory (class) for the feature and not the instance
itself. You'll see later why.

Now, a Client instance can use the service:

  >>> client = Client()
  >>> client.use_service()
  Service: I'm working hard

When you use the default :func:`provide` behavior, all instances of the Client
class will be injected the same Service instance:

  >>> another_client = Client()
  >>> client.service is another_client.service
  True

In fact, the default behavior when you :func:`provide` a feature is to create a
thread-local singleton that is injected in all instances that request the
feature. That's what we call the *scope*: it defines the lifespan of the
feature instance.

You may want a different ``IService`` instance for each Client. You can do that
by changing the default scope to :attr:`Scope.Transient` when you provide the
feature:

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
    in every circumstance."""

    Application = 'Application'
    """One instance per application (subject to thread-safety issues)"""

    Thread = 'Thread'
    """One instance per thread: this is the default"""

    Transient = 'Transient'
    """A new instance is created each time the feature is requested"""

    Request = 'Request'
    """One instance per HTTP request"""

    Session = 'Session'
    """One instance per HTTP session"""


class UndefinedScopeError(Exception):
    """Exception raised when using a scope that has not been entered yet."""


class ScopeManager(threading.local):
    """Manages scope contexts where we store the instances to be used for the
    injection."""

    def __init__(self):
        """Creates a new scope manager."""
        self._context = {}
        self._context[Scope.Thread] = {}
        self._context[Scope.Application] = _ApplicationContext

    def enter_scope(self, scope, context=None):
        """Called when we enter a *scope*. You can eventually provide the
        *context* to be used in this *scope*, that is, a dictionary of
        the instances to be injected for each feature. This is especially
        useful for implementing session scopes, when we want to reinstall
        a previous context."""
        self._context[scope] = context if context is not None else {}

    def exit_scope(self, scope):
        """Called when we exit the *scope*. Clear the context for this
        *scope*."""
        del self._context[scope]

    def context(self, scope):
        """Get the context for the *scope*, that is a dictionary of the
        feature instances. Raises a :exc:`UndefinedScopeError` if the
        *scope* is not yet defined."""
        if scope != Scope.Transient:
            scope_context = self._context.get(scope)
        else:
            scope_context = {}

        if scope_context is None:
            raise UndefinedScopeError("No scope defined for " + scope)

        return scope_context


class ScopeContext(object):
    """Context manager that defines the lifespan of a scope."""

    def __init__(self, scope, context=None, scope_manager=None):
        """Creates a scope context for the specified *scope*. If *context*
        is passed a dictionary, the created instances will be stored in
        this dictionary. Otherwise, a new dictionary will be created for
        storing instance each time we enter the scope. So the *context*
        argument can be used to recall a previous context. If *scope_manager*
        is specified, contexts will be stored in this *scope_manager*.
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
    """Provides the feature instances for injection when requested. It creates
    instances when necessary and uses the scope manager to obtain the scoped
    contexts where we store the feature instances."""

    def __init__(self, scope_manager=None):
        """Creates a feature provider. If *scope_manager* is specified,
        feature instances will be stored in the contexts of the
        *scope_manager*. Otherwise, the default scope manager will be
        used."""
        self.scope_manager = scope_manager or _DefaultScopeManager
        self.clear()

    def clear(self):
        """Unregister all features."""
        self._feature_descriptors = {}

    def provide(self, feature, factory, scope=Scope.Thread):
        """Provide a *factory* that build (scoped) instances of the *feature*.
        By default, the scope of the *feature* instance is :attr:`Scope.Thread`,
        but you can change this by providing a *scope* parameter.

        Note that you can change the factory for a feature by providing the
        same feature again, but the injected instances that already have a
        reference on the feature instance will not get a new instance."""
        self._feature_descriptors[feature] = (factory, scope)

    def get(self, feature):
        """Retrieve a (scoped) feature instance. Either find the instance in
        the associated context or create a new instance using the factory
        method and store it in the context."""
        feature_descriptor = self._feature_descriptors.get(feature)
        if feature_descriptor is None:
            raise MissingFeatureError("No feature provided for " + feature)
        factory, scope = feature_descriptor
        scope_context = self.scope_manager.context(scope)

        # acquire the lock
        if scope == Scope.Application:
            lock = threading.Lock()
            lock.acquire()

        # get or create the feature instance
        instance = scope_context.get(feature)
        if instance is None:
            instance = factory()
            scope_context[feature] = instance
            log.debug('New instance %r created in scope %s for the feature %r'
                      % (instance, scope, feature))
        else:
            log.debug('Found %r in scope %s for the feature %r'
                      % (instance, scope, feature))

        # release the lock
        if scope == Scope.Application:
            lock.release()

        return instance

    __getitem__ = get  # for convenience


class Attr(object):
    """Descriptor that provides attribute-based dependency injection."""

    def __init__(self, feature, provider=None):
        """Inject a *feature* as an instance attribute. *feature* can be any 
        hashable identifier. If a *provider* is specified, the feature instance
        will be retrieved from this provider. Otherwise, the default
        feature provider will be used.
        
        Example:
          >>> from yaak import inject
          >>> class Client(object):
          ...   service = inject.Attr('IService')
        """
        self.feature = feature
        self.provider = provider or _DefaultFeatureProvider
        self._name = None  # cache for the attribute name

    def _find_name(self, type):
        """Look for the name of the attribute that references this
        descriptor."""
        for cls in type.__mro__:  # support inheritance of injected classes
            for key, value in cls.__dict__.items():
                if value is self:
                    return key

    def __get__(self, obj, type=None):
        """Descriptor protocol: bind a feature instance to the object passed
        to the descriptor."""
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
        log.debug('%r has been injected into the attribute %r of %r'
                  % (feature, self._name, obj))

        return feature


class Param(object):
    """Decorator that provides parameter-based dependency injection."""

    def __init__(self, provider=None, **injections):
        """Inject feature instances into function parameters. First, specify
        the parameters that should be injected as keyword arguments (e.g.
        ``param=<feature>`` where ``<feature>`` is the feature identifier).
        Then, each time the function will be called, the parameters will
        receive feature instances. If a *provider* is specified, the feature
        instances will be retrieved from this provider. Otherwise, the default
        feature provider will be used.
        
        Example:
          >>> from yaak import inject
          >>> class Client(object):
          ...   inject.Param(service='IService')
          ...   def func(self, service):
          ...     pass  # use service
        """
        self.injections = injections
        self.provider = provider or _DefaultFeatureProvider

    def __call__(self, wrapped):
        """Decorator protocol"""
        if inspect.isclass(wrapped):
            # support class injection by injecting the __init__ method
            wrapped.__init__ = self._wrap(wrapped.__init__)
            return wrapped
        else:
            return self._wrap(wrapped)

    def _wrap(self, func):
        """Wrap a function so that one parameter is automatically injected
        and the other parameters should be passed to the wrapper function in
        the same order as in the wrapped function, or by keyword arguments"""
        # deal with stacked decorators: find the original function and the
        # injected parameters
        injected_params = getattr(func, 'injected_params', {})
        injected_function = getattr(func, 'injected_function', func)

        def get_feature(feature, param):
            instance = provider.get(feature)
            msg = ('%r has been injected into the parameter %r of %r'
                   % (instance, param, injected_function))
            log.debug(msg)
            return instance

        # add the new injected parameter
        callable_provider = isinstance(self.provider, collections.Callable)
        provider = self.provider() if callable_provider else self.provider
        for param, feature in self.injections.items():
            binding = late_binding(lambda feature=feature, param=param:
                                   get_feature(feature, param))
            injected_params[param] = binding

        # inject it (functools.partial is not suitable here)
        new_func = bind(injected_function, **injected_params)
        new_func.injected_params = injected_params
        new_func.injected_function = injected_function
        functools.update_wrapper(new_func, injected_function)

        return new_func


class BindNotSupportedError(Exception):
    """Exception raised when a function could not be used in the bind method."""


def bind(func, **frozen_args):
    """This function is similar to the :func:`functools.partial` function: it
    implements partial application. That is, it's a way to transform a function
    to another function with less arguments, because some of the arguments of
    the original function will get some fixed values: these arguments are
    called frozen arguments. But unlike the :func:`functools.partial` function, 
    the frozen parameters can be anywhere in the signature of the transformed
    function, they are not required to be the first or last ones. Also, you
    can pass a :func:`late_binding` function as the value of a parameter
    to get the value from a call to this function when the bound function is
    called (this implements late binding).

    Say you have a function :func:`add` defined like this::

      >>> def add(a, b):
      ...   return a + b

    You can bind the parameter *b* to the value 1::

      >>> add_one = bind(add, b=1)

    Now, :func:`add_one` has only one parameters *a* since *b* will always
    get the value 1. So::

      >>> add_one(1)
      2
      >>> add_one(2)
      3
      
    Now, an example of late binding::
      
      >>> import itertools
      >>> count = itertools.count(0)
      >>> def more_and_more():
      ...   return count.next()
      ...
      >>> add_more_and_more = bind(add, b=late_binding(more_and_more)) 
      >>> add_more_and_more(1)
      1
      >>> add_more_and_more(1)
      2
      >>> add_more_and_more(1)
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
        raise BindNotSupportedError(msg)

    def inner_func(*inner_args, **inner_kwargs):
        # call the value if it is a late binding factory
        def resolve(value):
            if getattr(value, '__late_binding_factory__', False):
                return value()
            else:
                return value

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
                msg = ("%s() got multiple values for keyword argument '%s'"
                       % (func.__name__, arg))
                raise TypeError(msg)

            # OK, use the next positional argument
            arg_dict[arg] = inner_args[arg_idx]
            arg_idx += 1

        # call the bound function with the extended arguments list
        arg_dict.update(inner_kwargs)
        return func(**arg_dict)

    return inner_func


def late_binding(func):
    """Create a late binding by providing a factory function to be called when
    the bound function is called"""
    func.__late_binding_factory__ = True
    return func
#



class WSGIRequestScope(object):
    """WSGI middleware that installs the :attr:`Scope.Request` contexts for
    the wrapped application."""

    def __init__(self, app, scope_manager=None):
        """Installs :attr:`Scope.Request` contexts for the application *app*.
        That is, a new context will be used in each HTTP request for storing the
        Request scoped features. You can eventually pass the *scope_manager*
        that will handle the scope contexts. Otherwise, the default scope
        manager will be used."""
        self.app = app
        self.scope_manager = scope_manager

    def __call__(self, environ, start_response):
        """WSGI protocol"""
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
""":meth:`provide` a feature to the default feature provider"""

get = _DefaultFeatureProvider.get
""":meth:`get` a feature from the default feature provider"""

clear = _DefaultFeatureProvider.clear
""":meth:`clear` the features from the default feature provider"""
