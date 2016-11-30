
import unittest
import browsepy.event


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
        self.manager.test.append(a.append)
        self.manager.test.append(a.append)
        self.manager.test(1)
        self.manager.test(2)
        self.assertListEqual(a, [1, 1, 2, 2])
