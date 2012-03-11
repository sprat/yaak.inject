# -*- coding: UTF-8 -*-
# Copyright (c) 2011-2012 Sylvain Prat. This program is open-source software,
# and may be redistributed under the terms of the MIT license. See the
# LICENSE file in this distribution for details.

import unittest
import threading

from yaak import inject


def run_in_thread(func):
    """Utility function that runs a function in a separate thread and
    returns its result."""
    def target():
        target.result = func()  # store the result in the function __dict__

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    return target.result


class TestScopeManager(unittest.TestCase):
    def setUp(self):
        self.scope_manager = inject.ScopeManager()

    def store_in_context(self, scope, key, value):
        self.scope_manager.get_or_create(scope, key, lambda: value)

    def test_scope_application(self):
        try:
            self.store_in_context(inject.Scope.Application, 'test', 'test')
            context, _ = self.scope_manager._get_context(inject.Scope.Application)
            self.assertEquals(dict(test='test'), context)
            context, _ = run_in_thread(
                lambda: self.scope_manager._get_context(inject.Scope.Application))
            self.assertEquals(dict(test='test'), context)
        finally:
            self.scope_manager.clear_context(inject.Scope.Application)

    def test_scope_transient(self):
        self.store_in_context(inject.Scope.Transient, 'test', 'test')
        context, _ = self.scope_manager._get_context(inject.Scope.Transient)
        self.assertEquals({}, context)

    def test_scope_thread(self):
        self.store_in_context(inject.Scope.Thread, 'test', 'test')
        context, _ = self.scope_manager._get_context(inject.Scope.Thread)
        self.assertEquals(dict(test='test'), context)
        context, _ = run_in_thread(
            lambda: self.scope_manager._get_context(inject.Scope.Thread))
        self.assertEquals({}, context)

    def test_fail_when_we_try_to_use_an_undeclared_scope(self):
        self.assertRaises(inject.UndefinedScopeError,
                          lambda: self.scope_manager._get_context('MyScope'))

    def test_enter_exit_scope(self):
        self.scope_manager.enter_scope('MyScope')
        self.store_in_context('MyScope', 'test', 'test')
        self.assertEquals((dict(test='test'), None),
                          self.scope_manager._get_context('MyScope'))
        self.scope_manager.exit_scope('MyScope')
        self.assertRaises(inject.UndefinedScopeError,
                          lambda: self.scope_manager._get_context('MyScope'))

    def test_enter_scope_error(self):
        self.scope_manager.enter_scope('MyScope')
        self.assertRaises(inject.ScopeReenterError,
                          lambda: self.scope_manager.enter_scope('MyScope'))

    def test_exit_scope_error(self):
        self.assertRaises(inject.UndefinedScopeError,
                          lambda: self.scope_manager.exit_scope('MyScope'))

    def test_enter_exit_scope_with_context(self):
        context = dict(test='test')
        self.scope_manager.enter_scope('MyScope', context)
        self.assertEquals((dict(test='test'), None),
                          self.scope_manager._get_context('MyScope'))
        self.scope_manager.exit_scope('MyScope')
        self.assertRaises(inject.UndefinedScopeError,
                          lambda: self.scope_manager._get_context('MyScope'))


class TestScopeContext(unittest.TestCase):
    def setUp(self):
        # use a new scope manager for each test!
        self.scope_manager = inject.ScopeManager()
        self.provider = inject.FeatureProvider(self.scope_manager)
        self.instance = object()
        self.provider.provide('instance',
                              lambda: self.instance,
                              scope=inject.Scope.Request)

    def test_with(self):
        self.assertRaises(inject.UndefinedScopeError,
                          lambda: self.provider.get('instance'))
        with inject.ScopeContext(inject.Scope.Request,
                                 scope_manager=self.scope_manager):
            instance = self.provider.get('instance')
            self.assert_(instance is self.instance)
        self.assertRaises(inject.UndefinedScopeError,
                          lambda: self.provider.get('instance'))


class TestFeatureProvider(unittest.TestCase):
    def setUp(self):
        # use a new scope manager for each test!
        self.provider = inject.FeatureProvider(inject.ScopeManager())

    def provide_singleton(self, feature_name):
        """Utility method that provides a singleton instance and returns it."""
        singleton = object()
        self.provider.provide(feature_name, lambda: singleton)
        return singleton

    def test_provide_singleton(self):
        o = self.provide_singleton('singleton')
        self.assertEquals(o, self.provider.get('singleton'))

    def test_provide_none(self):
        def create_none():
            create_none.calls += 1
            return None
        create_none.calls = 0
        self.provider.provide('test', create_none)
        self.assertEquals(None, self.provider.get('test'))
        self.provider.get('test')
        self.assertEquals(1, create_none.calls)

    def test_provide_class_in_application_scope(self):
        try:
            class Factory():
                pass

            self.provider.provide('factory',
                                  Factory,
                                  scope=inject.Scope.Application)
            f1 = self.provider.get('factory')
            f2 = self.provider.get('factory')
            self.assert_(f1 is f2)
            self.assert_(isinstance(f1, Factory))
        finally:
            scope_manager = self.provider.scope_manager
            scope_manager.clear_context(inject.Scope.Application)

    def test_provide_class_in_transient_scope(self):
        class Factory():
            pass

        self.provider.provide('factory', Factory, inject.Scope.Transient)
        f1 = self.provider.get('factory')
        f2 = self.provider.get('factory')
        self.assert_(not f1 is f2)
        self.assert_(isinstance(f1, Factory))
        self.assert_(isinstance(f2, Factory))

    def test_provide_accept_special_characters_for_feature_name(self):
        special_names = ['name with spaces', '#@name']
        for name in special_names:
            o = self.provide_singleton(name)
            self.assertEquals(o, self.provider.get(name))

    def test_provide_also_accept_non_string_identifiers(self):
        class Interface(object):
            pass

        o = self.provide_singleton(Interface)
        self.assertEquals(o, self.provider.get(Interface))

    def test_an_exception_is_raised_when_accessing_a_missing_feature(self):
        self.assertRaises(inject.MissingFeatureError,
                          lambda: self.provider.get('invalid_feature'))

    def test_scope_thread(self):
        self.provider.provide('singleton', object, scope=inject.Scope.Thread)

        o1 = self.provider.get('singleton')
        o_thread = run_in_thread(lambda: self.provider.get('singleton'))
        o2 = self.provider.get('singleton')

        self.assert_(o1 is o2)
        self.assert_(not o1 is o_thread)

    def test_scope_application(self):
        try:
            self.provider.provide('singleton', object,
                                  scope=inject.Scope.Application)
            o = self.provider.get('singleton')
            o_thread = run_in_thread(lambda: self.provider.get('singleton'))
            self.assert_(o is o_thread)
        finally:
            scope_manager = self.provider.scope_manager
            scope_manager.clear_context(inject.Scope.Application)

    def test_invalid_scope(self):
        self.provider.provide('singleton', object, scope='oops')
        self.assertRaises(inject.UndefinedScopeError,
                          lambda: self.provider.get('singleton'))


class TestAttr(unittest.TestCase):
    def setUp(self):
        # use a new scope manager for each test!
        self.provider = inject.FeatureProvider(inject.ScopeManager())

        class Injected(object):
            service = inject.Attr('service', self.provider)
            another_service = inject.Attr('service', self.provider)

        self.Injected = Injected

    def test_default_provider_is_used_when_no_provider_is_passed(self):
        try:
            class AnotherInjected(object):
                service = inject.Attr('service')
            singleton = object()
            inject.provide('service', lambda: singleton)
            o = AnotherInjected()
            self.assert_(o.service is singleton)
        finally:
            inject.clear()  # cleanup after test

    def test_class_binding(self):
        singleton = object()
        self.provider.provide('service', lambda: singleton)
        self.assertRaises(AttributeError, getattr, self.Injected, 'service')

    def test_same_instance_when_accessing_a_singleton_feature_twice(self):
        self.provider.provide('service', object)
        o = self.Injected()
        instance1 = o.service
        instance2 = o.service
        self.assert_(instance1 is instance2)

    def test_same_instance_when_accessing_a_transient_feature_twice(self):
        self.provider.provide('service', object, scope=inject.Scope.Transient)
        o = self.Injected()
        instance1 = o.service
        instance2 = o.service
        self.assert_(instance1 is instance2)

    def test_different_instances_when_accessing_two_transient_attributes(self):
        self.provider.provide('service', object, scope=inject.Scope.Transient)
        o = self.Injected()
        self.assert_(not o.service is o.another_service)

    def test_missing_feature(self):
        o = self.Injected()
        self.assertRaises(inject.MissingFeatureError, lambda: o.service)

    def test_inheritance(self):
        class Inherited(self.Injected):
            pass
        singleton = object()
        self.provider.provide('service', lambda: singleton)
        o = Inherited()
        self.assert_(o.service is singleton)


class TestParam(unittest.TestCase):
    def setUp(self):
        class Mirror(object):
            def reflect(self, a):
                return a
        self.provider = inject.FeatureProvider(inject.ScopeManager())
        self.provider.provide('IMirror', Mirror)
        self.inject_mirror = inject.Param(self.provider, mirror='IMirror')

    def test_one_injected_parameter_only(self):
        @self.inject_mirror
        def func(mirror):
            return mirror.reflect('test')

        self.assertEquals('test', func())

    def test_one_normal_parameter_then_one_injected(self):
        @self.inject_mirror
        def func(a, mirror):
            return mirror.reflect(a)

        self.assertEquals('test', func('test'))

    def test_one_injected_parameter_then_one_normal(self):
        @self.inject_mirror
        def func(mirror, a):
            return mirror.reflect(a)

        self.assertEquals('test', func('test'))

    def test_stacked_injections(self):
        self.provider.provide('IParam', lambda: 'test')

        @self.inject_mirror
        @inject.Param(self.provider, a='IParam')
        def func(mirror, a):
            return mirror.reflect(a)

        self.assertEquals('test', func())

    def test_multiple_injections(self):
        self.provider.provide('IParam', lambda: 'test')

        @inject.Param(self.provider, mirror='IMirror', a='IParam')
        def func(mirror, a):
            return mirror.reflect(a)

        self.assertEquals('test', func())

    def test_with_method(self):
        self.provider.provide('Value', lambda: 10)

        class Offset(object):
            @inject.Param(self.provider, value='Value')
            def __init__(self, value):
                self.value = value

        o = Offset()
        self.assertEquals(10, o.value)

    def test_with_class(self):
        self.provider.provide('Value', lambda: 10)

        @inject.Param(self.provider, value='Value')
        class Offset(object):
            def __init__(self, value):
                self.value = value

        o = Offset()
        self.assertEquals(10, o.value)


class TestBind(unittest.TestCase):
    def test_bind_first_arg_with_positional_second_arg(self):
        def func(a, b):
            return a + 2 * b
        func = inject.bind(func, a=1)
        self.assertEqual(5, func(2))

    def test_bind_first_arg_with_default_second_arg(self):
        def func(a, b=5):
            return a + 2 * b
        func = inject.bind(func, a=1)
        self.assertEqual(11, func())

    def test_bind_first_arg_with_keyword_second_arg(self):
        def func(a, b):
            return a + 2 * b
        func = inject.bind(func, a=1)
        self.assertEqual(7, func(b=3))

    def test_we_can_override_a_bound_argument(self):
        def func(a, b):
            return a + 2 * b
        func = inject.bind(func, a=1)
        self.assertEqual(8, func(a=2, b=3))

    def test_fail_if_we_miss_an_argument(self):
        def func(a, b):
            return a + 2 * b
        func = inject.bind(func, a=1)
        self.assertRaises(TypeError, func)

    def test_fail_when_passing_a_normal_argument_twice(self):
        def func(a, b):
            return a + 2 * b
        func = inject.bind(func, a=1)
        self.assertRaises(TypeError, lambda: func(3, b=3))

    def test_bind_last_arg(self):
        def func(a, b):
            return a + 2 * b
        func = inject.bind(func, b=1)
        self.assertEqual(4, func(2))

    def test_bind_middle_arg(self):
        def func(a, b, c):
            return a + 2 * b + 3 * c
        func = inject.bind(func, b=1)
        self.assertEqual(13, func(2, 3))

    def test_bind_function_arg(self):
        def func(a, b):
            return b(a)
        func = inject.bind(func, b=lambda x: x * x)
        self.assertEqual(4, func(2))

    def test_bind_with_late_binding(self):
        def func(a, b):
            return a + 2 * b
        func = inject.bind(func, b=inject.late_binding(lambda: 1))
        self.assertEqual(4, func(2))

    def test_bind_fail_with_varargs(self):
        def func(a, *args):
            return (a, args)
        self.assertRaises(inject.BindNotSupportedError,
                          lambda: inject.bind(func, a=0))

    def test_bind_work_with_keyword_args(self):
        def func(a, **kwargs):
            return a, kwargs
        func = inject.bind(func, a=1)
        self.assertEquals((1, dict(b=1, c=1)), func(b=1, c=1))

    def test_bind_bound_method(self):
        class Offset(object):
            def __init__(self, value):
                self.value = value

            def add(self, a, b):
                return self.value + a + b

        func = inject.bind(Offset(5).add, a=2)
        self.assertEquals(10, func(3))

    def test_bind_unbound_method(self):
        class Offset(object):
            def __init__(self, value):
                self.value = value

            def add(self, a, b):
                return self.value + a + b

        func = inject.bind(Offset.add, a=2)
        self.assertEquals(10, func(Offset(5), 3))

    def test_method_replacement(self):
        class Offset(object):
            def __init__(self, value):
                self.value = value

            def add(self, a, b):
                return self.value + a + b

            add = inject.bind(add, a=2)

        self.assertEquals(10, Offset(5).add(3))


class TestWSGIRequestScope(unittest.TestCase):
    class WSGIAppStub(object):
        def __call__(self, environ, start_response):
            provider = environ['provider']
            start_response("200 OK", [])
            yield provider.get('test')

    def start_response(self, status, response_headers, exc_info=None):
        return None

    def test_app(self):
        scope_manager = inject.ScopeManager()
        provider = inject.FeatureProvider(scope_manager)
        provider.provide('test', object, inject.Scope.Request)

        app = inject.WSGIRequestScope(self.WSGIAppStub(), scope_manager)

        result1 = list(app(dict(provider=provider), self.start_response))
        self.assert_(isinstance(result1[0], object))
        result2 = run_in_thread(lambda: list(app(dict(provider=provider),
                                                 self.start_response)))
        self.assert_(isinstance(result2[0], object))
        self.assert_(not result1[0] is result2[0])


if __name__ == '__main__':
    unittest.main()
