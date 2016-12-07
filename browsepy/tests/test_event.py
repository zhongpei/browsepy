
import os
import os.path
import tempfile
import contextlib
import shutil
import unittest
import collections
import browsepy.event
import browsepy.manager
import threading


class EventTest(unittest.TestCase):
    module = browsepy.event

    def setUp(self):
        self.event = self.module.Event()

    def test_call(self):
        a = []
        self.event.append(a.append)
        self.event.append(a.append)
        self.event(1)
        self.assertListEqual(a, [1, 1])

    def test_thread_safety(self):
        a = []
        self.event.append(lambda x: self.event(x + 1) if x < 2 else None)
        self.event.append(a.append)
        self.event.append(a.append)
        self.event(1)
        self.assertListEqual(a, [1, 1, 2, 2])


class EventManagerTest(unittest.TestCase):
    module = browsepy.event

    def setUp(self):
        self.manager = self.module.EventManager()

    def test_subscribe(self):
        a = []
        self.manager['test'].append(a.append)
        self.manager['test'].append(a.append)
        self.manager['test'](1)
        self.manager['test'](2)
        self.assertListEqual(a, [1, 1, 2, 2])


class WatchdogEventSourceTest(unittest.TestCase):
    module = browsepy.event
    app_class = collections.namedtuple('App', ('config',))
    event_class = threading.Event

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.manager = self.module.EventManager()
        self.source = self.module.WatchdogEventSource(
            self.manager,
            self.app_class(config={
                'base_directory': self.base
                })
            )

    @contextlib.contextmanager
    def assertEvents(self, *etypes,
                     handler_factory=(lambda evt: (lambda e: evt.set()))):
        evts = [
            (etype, event, handler_factory(event))
            for etype in etypes
            for etype, event in ((etype, self.event_class()),)
            ]
        for etype, event, handler in evts:
            self.manager[etype].append(handler)
        yield
        for etype, event, handler in evts:
            self.assertTrue(
                event.wait(timeout=1),
                'Event %r not received' % etype
                )
            self.manager[etype].remove(handler)

    def tearDown(self):
        self.source.clear()
        shutil.rmtree(self.base)

    def test_events(self):
        events = []
        base = self.base
        filepath = os.path.join(self.base, 'file')
        dirpath = os.path.join(self.base, 'dir')

        self.manager['fs_any'].append(
            lambda e: events.append((e.type, e.path))
            )

        with self.assertEvents('fs_any', 'fs_create', 'fs_modify',
                               'fs_create_file', 'fs_modify_directory'):
            open(filepath, 'w').close()

        with self.assertEvents('fs_any', 'fs_modify',
                               'fs_modify_file'):
            with open(filepath, 'w') as f:
                f.write('a')
                f.close()

        with self.assertEvents('fs_any', 'fs_remove', 'fs_modify',
                               'fs_modify_directory'):
            os.remove(filepath)

        with self.assertEvents('fs_any', 'fs_create', 'fs_modify',
                               'fs_create_directory', 'fs_modify_directory'):
            os.mkdir(dirpath)

        with self.assertEvents('fs_any', 'fs_remove', 'fs_modify',
                               'fs_modify_directory'):
            os.rmdir(dirpath)

        self.assertListEqual(events, [
            ('fs_create', filepath),
            ('fs_modify', base),
            ('fs_modify', filepath),
            ('fs_remove', filepath),
            ('fs_modify', base),
            ('fs_create', dirpath),
            ('fs_modify', base),
            ('fs_remove', dirpath),
            ('fs_modify', base),
            ])


class ManagerTest(unittest.TestCase):
    module = browsepy.manager
    source_class = browsepy.event.WatchdogEventSource

    def test_default_sources(self):
        class app(object):
            config = {
                'disk_cache_enable': False
                }
        manager = self.module.EventPluginManager(app)
        self.assertFalse(manager.has_event_source(self.source_class))
        app.config['disk_cache_enable'] = True
        manager.reload()
        self.assertTrue(manager.has_event_source(self.source_class))

    def test_register_source(self):
        class source(object):
            def __init__(self, app, manager):
                pass

            @classmethod
            def check(cls, app):
                return True
        manager = self.module.EventPluginManager()
        self.assertFalse(manager.has_event_source(source))
        manager.register_event_source(source)
        self.assertTrue(manager.has_event_source(source))
