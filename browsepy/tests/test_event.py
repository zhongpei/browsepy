
import os
import os.path
import tempfile
import shutil
import unittest
import collections
import browsepy.event
import browsepy.manager
import browsepy.tests.utils as test_utils


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
        self.events = self.module.EventManager()

    def test_subscribe(self):
        a = []
        self.events['test'].append(a.append)
        self.events['test'].append(a.append)
        self.events['test'](1)
        self.events['test'](2)
        self.assertListEqual(a, [1, 1, 2, 2])


class WatchdogEventSourceTest(test_utils.EventTestCase):
    module = browsepy.event
    app_class = collections.namedtuple('App', ('config',))

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.events = self.module.EventManager()
        self.source = self.module.WatchdogEventSource(
            self.events,
            self.app_class(config={
                'base_directory': self.base
                })
            )

    def tearDown(self):
        self.source.clear()
        shutil.rmtree(self.base)

    def test_events(self):
        events = []
        base = self.base
        filepath = os.path.join(self.base, 'file')
        dirpath = os.path.join(self.base, 'dir')

        self.events['fs_any'].append(
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
