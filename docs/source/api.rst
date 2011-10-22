=============================================
 API Documentation for yaak.inject |release|
=============================================


Defining the injected features
==============================

The Dependency Injection can be performed either by attribute injection or
parameter injection:

.. autoclass:: yaak.inject.Attr

.. autoclass:: yaak.inject.Param


Providing the features
======================

.. autoclass:: yaak.inject.FeatureProvider


Scopes
======

.. autoclass:: yaak.inject.Scope

.. autoclass:: yaak.inject.ScopeManager

.. autoclass:: yaak.inject.ScopeContext

.. autoclass:: yaak.inject.WSGIRequestScope


Using the default feature provider
==================================

.. autofunction:: yaak.inject.provide

.. autofunction:: yaak.inject.get

.. autofunction:: yaak.inject.clear


Helper tools
============

.. autofunction:: yaak.inject.bind

.. autofunction:: yaak.inject.late_binding


Exceptions
==========

.. autoexception:: yaak.inject.MissingFeatureError
   
.. autoexception:: yaak.inject.UndefinedScopeError

.. autoexception:: yaak.inject.BindNotSupportedError
