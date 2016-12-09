
import flask
import unittest
import contextlib
import threading


def clear_localstack(stack):
    '''
    Clear given werkzeug LocalStack instance.

    :param ctx: local stack instance
    :type ctx: werkzeug.local.LocalStack
    '''
    while stack.pop():
        pass


def clear_flask_context():
    '''
    Clear flask current_app and request globals.

    When using :meth:`flask.Flask.test_client`, even as context manager,
    the flask's globals :attr:`flask.current_app` and :attr:`flask.request`
    are left dirty, so testing code relying on them will probably fail.

    This function clean said globals, and should be called after testing
    with :meth:`flask.Flask.test_client`.
    '''
    clear_localstack(flask._app_ctx_stack)
    clear_localstack(flask._request_ctx_stack)


def defaultHandlerFactory(evt):
    '''
    Default handler factory for :meth:`EventTestCase.assertEvents`.

    :param evt: threading event object
    :type evt: threading.Event
    :returns: function accepting a browsepy event and setting threading event
    :rtype: callable
    '''
    return lambda e: evt.set()


class EventTestCase(unittest.TestCase):
    event_class = threading.Event

    @contextlib.contextmanager
    def assertEvents(self, *etypes, handler_factory=defaultHandlerFactory):
        evts = [
            (etype, event, handler_factory(event))
            for etype in etypes
            for etype, event in ((etype, self.event_class()),)
            ]
        for etype, event, handler in evts:
            self.events[etype].append(handler)
        yield
        for etype, event, handler in evts:
            self.assertTrue(
                event.wait(timeout=1),
                'Event %r not received' % etype
                )
            self.events[etype].remove(handler)
