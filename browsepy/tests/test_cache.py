
import unittest

import browsepy.cache as browsepy_cache
import browsepy.manager as browsepy_manager


class TestCache(unittest.TestCase):
    module = browsepy_cache

    def test_interface(self):
        cache = self.module.SimpleLRUCache()
        self.assertIsNone(cache.get('a'))
        self.assertFalse(cache.has('a'))
        self.assertTrue(cache.set('a', 1))
        self.assertTrue(cache.has('a'))
        self.assertEqual(cache.get('a'), 1)
        self.assertEqual(cache.inc('a'), 2)
        self.assertEqual(cache.dec('a'), 1)
        self.assertTrue(cache.clear())
        self.assertFalse(cache.has('a'))
        self.assertIsNone(cache.get('a'))
        self.assertTrue(cache.set_many({'a': 1, 'b': 2}))
        self.assertListEqual(cache.get_many('a', 'b'), [1, 2])
        self.assertDictEqual(cache.get_dict('a', 'b'), {'a': 1, 'b': 2})
        self.assertTrue(cache.set('c', 3))
        self.assertTrue(cache.delete_many('a', 'b'))
        self.assertListEqual(cache.get_many('a', 'b'), [None, None])
        self.assertDictEqual(cache.get_dict('a', 'b'), {'a': None, 'b': None})
        self.assertEqual(cache.get('c'), 3)
        self.assertTrue(cache.delete('c'))
        self.assertListEqual(cache.get_many('a', 'b', 'c'), [None, None, None])

    def test_maxsize(self):
        cache = self.module.SimpleLRUCache(maxsize=2)
        self.assertTrue(cache.set('a', 1))
        self.assertTrue(cache.set('b', 2))
        self.assertListEqual(cache.get_many('a', 'b'), [1, 2])
        self.assertTrue(cache.set('c', 3))
        self.assertListEqual(cache.get_many('a', 'b', 'c'), [None, 2, 3])


class TestManager(unittest.TestCase):
    module = browsepy_manager

    def test_manager(self):
        manager = self.module.CachePluginManager()
        self.assertIsInstance(manager.cache, browsepy_cache.SimpleLRUCache)
