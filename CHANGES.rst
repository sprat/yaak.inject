Changelog
=========


0.2.2 (?)
---------------------

* The project is now hosted on Github instead of Bitbucket
* Bugfix: the Attr's injected instances were not rebound when the associated
  scope changed
* Simpler implementation of the ``bind`` function. Should be faster too!
* The ``bind`` function can now be used on functions with varargs
* The ``bind`` function can now be used as a decorator
* The ``bind`` function doesn't allow the override of injected parameters
  anymore: it was a bad idea!
* The ``provide`` method/function can now be used as a decorator
* Removed the ``late_binding`` feature since it was not necessary: if you want
  to bind an argument with a function object but don't want it to be called
  during the binding, put it inside a lambda.
* Removed logging to reduce clutter: the user can log whatever he wants by
  subclassing our classes
* PEP8 conformance


0.2.1 (11-March-2012)
---------------------

* The setup.py file does not import code anymore in order to retrieve the
  version information, since it may cause some installation problems
* Fixed bad years in the changelog, and reordered the items so that the most
  recent changes appear first
* Changed the aliases for releasing new versions
* Fixed line endings (unix style)
* Removed the extensions of the text files since it's a convention in the
  Python world


0.2.0 (24-Oct-2011)
-------------------

* Fixed the broken lock acquire/release implementation when updating the
  application context dictionary
* The locking mechanism is now available for all scopes
* The context manager is now responsible for updating the context dictionaries
* Fixed duplicate factory calls when providing a factory returning None
* ScopeManager.enter_scope now raise a ScopeReenterError when re-entering a
  scope
* ScopeManager.exit_scope now raise a UndefinedScopeError when exiting an
  undeclared scope
* Fixed the API documentation


0.1.0 (23-Oct-2011)
-------------------

* Initial release
