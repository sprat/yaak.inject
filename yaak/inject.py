# -*- coding: utf-8 -*-
# Copyright (c) 2011-2012 Sylvain Prat. This program is open-source software,
# and may be redistributed under the terms of the MIT license. See the
# LICENSE file in this distribution for details.

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

When you use the default :func:`provide` behavior, all instances
of the Client class will be injected the same Service instance:

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


__version__ = "0.2.1"


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


class ScopeError(Exception):
    """Base class for all scope related errors"""


class UndefinedScopeError(ScopeError):
    """Exception raised when using a scope that has not been entered yet."""


class ScopeReenterError(ScopeError):
    """Exception raised when re-entering a scope that has already been
    entered."""


# global application context
_ApplicationContext = {}
# global to acquire when updating the application context
_ApplicationContextLock = threading.Lock()


class ScopeManager(threading.local):
    """Manages scope contexts where we store the instances to be used for the
    injection."""
    # We use a thread-local storage because, when we enter/exit a scope, it is
    # only for the current thread. However, the context dictionaries may be
    # shared between the threads, so a context lock may be necessary to avoid
    # race conditions when updating the context dictionaries.

    def __init__(self):
        """Creates a new scope manager."""
        self._context = {}
        # install the Scope.Thread context
        self.enter_scope(Scope.Thread,
                         {})
        # install the Scope.Application context
        self.enter_scope(Scope.Application,
                         _ApplicationContext,
                         _ApplicationContextLock)

    def enter_scope(self, scope, context=None, context_lock=None):
        """Called when we enter a *scope*. You can eventually provide the
        *context* to be used in this *scope*, that is, a dictionary of
        the instances to be injected for each feature. This is especially
        useful for implementing session scopes, when we want to reinstall
        a previous context. You can also pass a lock to acquire when modifying
        the context dictionary via the parameter *context_lock* if the scope
        is subject to thread concurrency issues. Raises a
        :exc:`yaak.inject.ScopeReenterError` when re-entering an already
        entered *scope*."""
        if scope in self._context:
            raise ScopeReenterError("Scope %s already defined" % scope)
        self._context[scope] = (context if context is not None else {},
                                context_lock)

    def exit_scope(self, scope):
        """Called when we exit the *scope*. Remove the context for this
        *scope*. Raises a :exc:`yaak.inject.UndefinedScopeError` if the
        *scope* is not defined."""
        if not scope in self._context:
            raise UndefinedScopeError("No scope defined for " + scope)
        del self._context[scope]

    def _get_context(self, scope):
        """Get the context for the *scope*, that is a dictionary of the
        feature instances. Raises a :exc:`yaak.inject.UndefinedScopeError`
        if the *scope* is not defined."""
        if scope != Scope.Transient:
            context, lock = self._context.get(scope, (None, None))
        else:
            context, lock = {}, None

        if context is None:
            raise UndefinedScopeError("No scope defined for " + scope)

        return context, lock

    def clear_context(self, scope):
        """Clears the context for a *scope*, that is, remove all instances
        from the *scope* context."""
        # get the context dictionary for the scope or raise an error
        context, lock = self._get_context(scope)
        # acquire the context lock before modifying the context
        if lock:
            lock.acquire()
        # clear the context
        context.clear()
        # release the context lock
        if lock:
            lock.release()

    def get_or_create(self, scope, key, factory):
        """Get the value for a *key* from the *scope* context, or create one
        using the *factory* provided if there's no value for this *key*. Raises
        a :exc:`yaak.inject.UndefinedScopeError` if the *scope* is not
        defined."""
        # get the context dictionary for the scope or raise an error
        context, lock = self._get_context(scope)
        marker = object()
        # get or create the feature instance
        instance = context.get(key, marker)
        if instance is marker:
            # acquire the context lock before modifying the context
            if lock:
                lock.acquire()

            # re-check since the lock was not acquired in the first check
            instance = context.get(key, marker)
            if instance is marker:
                # create the instance
                instance = factory()
                context[key] = instance
                log.debug('New instance %r created in scope %s for the key %r'
                          % (instance, scope, key))

            # release the context lock
            if lock:
                lock.release()
        else:
            log.debug('Found %r in scope %s for the key %r'
                      % (instance, scope, key))

        return instance


# default scope manager instance
_DefaultScopeManager = ScopeManager()


class ScopeContext(object):
    """Context manager that defines the lifespan of a scope."""

    def __init__(self, scope, context=None, context_lock=None,
                 scope_manager=None):
        """Creates a scope context for the specified *scope*. If *context*
        is passed a dictionary, the created instances will be stored in
        this dictionary. Otherwise, a new dictionary will be created for
        storing instance each time we enter the scope. So the *context*
        argument can be used to recall a previous context. If *context_lock*
        is specified, the lock will be acquired/released when the context
        dictionary is updated, in order to avoid thread concurrency issues. 
        If *scope_manager* is specified, contexts will be stored in this
        *scope_manager*. Otherwise, the default scope manager will be used."""
        self.scope = scope
        self.context = context
        self.context_lock = context_lock
        self.scope_manager = scope_manager or _DefaultScopeManager

    def __enter__(self):
        self.scope_manager.enter_scope(self.scope,
                                       self.context,
                                       self.context_lock)
        return self

    def __exit__(self, type, value, traceback):
        self.scope_manager.exit_scope(self.scope)
        return False  # let the exception pass through


class WSGIRequestScope(object):
    """WSGI middleware that installs the :attr:`yaak.inject.Scope.Request`
    contexts for the wrapped application."""

    def __init__(self, app, scope_manager=None):
        """Installs a :attr:`yaak.inject.Scope.Request` context for the
        application *app*. That is, a new context will be used in each HTTP
        request for storing the request scoped features. You can eventually
        pass the *scope_manager* that will handle the scope contexts.
        Otherwise, the default scope manager will be used."""
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
        By default, the scope of the *feature* instance is
        :attr:`yaak.inject.Scope.Thread`, but you can change this by providing
        a *scope* parameter.

        Note that you can change the factory for a feature by providing the
        same feature again, but the injected instances that already have a
        reference on the feature instance will not get a new instance."""
        self._feature_descriptors[feature] = (factory, scope)

    def get(self, feature):
        """Retrieve a (scoped) feature instance. Either find the instance in
        the associated context or create a new instance using the factory
        method and store it in the context. Raises a
        :exc:`yaak.inject.MissingFeatureError` when no feature has been
        provided yet."""
        feature_descriptor = self._feature_descriptors.get(feature)
        if feature_descriptor is None:
            raise MissingFeatureError("No feature provided for " + feature)
        factory, scope = feature_descriptor
        return self.scope_manager.get_or_create(scope, feature, factory)

    __getitem__ = get  # for convenience


# the default feature provider instance
_DefaultFeatureProvider = FeatureProvider()


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
    """Exception raised when a function could not be used in the
    :meth:`yaak.inject.bind` method."""


def bind(func, **frozen_args):
    """This function is similar to the :func:`functools.partial` function: it
    implements partial application. That is, it's a way to transform a function
    to another function with less arguments, because some of the arguments of
    the original function will get some fixed values: these arguments are
    called frozen arguments. But unlike the :func:`functools.partial` function, 
    the frozen parameters can be anywhere in the signature of the transformed
    function, they are not required to be the first or last ones. Also, you
    can pass a :func:`yaak.inject.late_binding` function as the value of a
    parameter to get the value from a call to this function when the bound
    function is called (this implements late binding). Raises a
    :exc:`yaak.inject.BindNotSupportedError` when passing an unsupported
    function to bind, for example a function with variable arguments.

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


# module helpers
provide = _DefaultFeatureProvider.provide
"""Provides a *factory* for a *feature* to the default feature provider. See
:meth:`yaak.inject.FeatureProvider.provide` for more information."""

get = _DefaultFeatureProvider.get
"""Gets a *feature* from the default feature provider. See
:meth:`yaak.inject.FeatureProvider.get` for more information."""

clear = _DefaultFeatureProvider.clear
"""Clears the features from the default feature provider. See
:meth:`yaak.inject.FeatureProvider.clear` for more information."""
