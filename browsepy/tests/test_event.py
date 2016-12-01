
import os
import os.path
import tempfile
import shutil
import unittest
import collections
import browsepy.event
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


class WathdogEventSourceTest(unittest.TestCase):
    module = browsepy.event
    app_class = collections.namedtuple('App', ('config',))

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.manager = self.module.EventManager()
        self.source = self.module.WathdogEventSource(
            self.manager,
            self.app_class(config={
                'base_directory': self.base
                })
            )

    def waiter(self, etype):
        evt = threading.Event()
        self.manager[etype].append(lambda e: evt.set())
        return evt

    def tearDown(self):
        self.source.clear()
        shutil.rmtree(self.base)

    def test_events(self):
        events = []
        waiter = self.waiter('fs_any')

        @self.manager.fs_any.append
        def handler(e):
            events.append((
                e.type,
                '/' if e.path == self.base else e.path[len(self.base):]
            ))

        open(os.path.join(self.base, 'asdf'), 'w').close()
        self.assertTrue(waiter.wait(timeout=10))
        self.assertListEqual(events, [
            ('fs_create', '/asdf'),
            ('fs_modify', '/'),
            ])
