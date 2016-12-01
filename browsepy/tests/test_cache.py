
import unittest

import browsepy.cache as browsepy_cache


class TestCache(unittest.TestCase):
    module = browsepy_cache

    def test_cache(self):
        cache = self.module.LRUCache()
        data = [0]

        @cache.memoize
        def fnc():
            data[0] += 1
            return data[0]

        self.assertEqual(fnc(), 1)
        self.assertEqual(fnc(), 1)
        self.assertListEqual(data, [1])

    def test_maxsize(self):
        cache = self.module.LRUCache(2)
        data = {}

        @cache.memoize
        def fnc(k):
            data.setdefault(k, 0)
            data[k] += 1
            return data[k]

        self.assertEqual(fnc(0), 1)
        self.assertEqual(fnc(1), 1)
        self.assertEqual(fnc(2), 1)
        self.assertEqual(fnc(0), 2)
        self.assertDictEqual(data, {0: 2, 1: 1, 2: 1})

    def test_pop(self):
        cache = self.module.LRUCache()
        data = {}

        @cache.memoize
        def fnc(k):
            data.setdefault(k, 0)
            data[k] += 1
            return data[k]

        self.assertEqual(fnc(0), 1)
        self.assertEqual(fnc(1), 1)
        self.assertEqual(fnc(0), 1)
        self.assertEqual(fnc.cache.pop(0), 1)
        self.assertEqual(fnc(0), 2)
        self.assertEqual(fnc(1), 1)
        self.assertEqual(fnc(0), 2)
        self.assertDictEqual(data, {0: 2, 1: 1})

    def test_clear(self):
        cache = self.module.LRUCache()
        data = {}

        @cache.memoize
        def fnc(k):
            data.setdefault(k, 0)
            data[k] += 1
            return data[k]

        self.assertEqual(fnc(0), 1)
        self.assertEqual(fnc(1), 1)
        self.assertEqual(fnc(0), 1)
        fnc.cache.clear()
        self.assertEqual(fnc(0), 2)
        self.assertEqual(fnc(1), 2)
        self.assertEqual(fnc(0), 2)
        self.assertDictEqual(data, {0: 2, 1: 2})
