
import time
import threading

from werkzeug.contrib.cache import BaseCache


NOT_FOUND = object()


class SimpleLRUCache(BaseCache):
    '''
    Simple memory cache for simgle process environments. Thread safe using
    :attr:`lock_class` (threading.Lock)

    Cache object evicting least recently used objects (LRU) when maximum cache
    size is reached, so keys could be discarded independently of their
    timeout.

    '''
    lock_class = threading.Lock
    time_func = time.time

    @property
    def full(self):
        '''
        :returns: True if size reached maxsize, False otherwise
        :rtype: bool
        '''
        return self._full

    @property
    def size(self):
        '''
        :returns: current size of result cache
        :rtype: int
        '''
        return len(self._cache)

    @property
    def maxsize(self):
        '''
        :returns: maximum size of result cache
        :rtype: int
        '''
        return self._maxsize

    def __init__(self, default_timeout=300, maxsize=1024):
        self._default_timeout = default_timeout
        self._cache = {}
        self._full = False
        self._maxsize = maxsize
        self._lock = self.lock_class()
        self._key = None

    def _extract(self, link):
        PREV, NEXT, KEY = 0, 1, 2
        prev = link[PREV]
        if prev is link:
            self._key = None
            return link
        next = link[NEXT]
        prev[NEXT] = next
        next[PREV] = prev
        if link[KEY] == self._key:
            self._key = next[KEY]
        return link

    def _insert(self, link):
        PREV, NEXT, KEY = 0, 1, 2
        if self._cache:
            next = self._cache[self._key]
            prev = next[PREV]
            link[:2] = (prev, next)
            prev[NEXT] = link
            next[PREV] = link
        else:
            link[:2] = (link, link)
            self._key = link[KEY]
        return link

    def _shift(self, pop=False):
        NEXT, KEY = 1, 2
        if pop:
            link = self._cache.pop(self._key)
        else:
            link = self._cache[self._key]
        self._key = link[NEXT][KEY]
        return link

    def _bump(self, link):
        NEXT, KEY = 1, 2
        if link[KEY] == self._key:
            return self._shift()
        if link[NEXT][KEY] == self._key:
            return link
        return self._insert(self._extract(link))

    def _getitem(self, key, default=NOT_FOUND):
        VALUE, EXPIRE = 3, 4
        link = self._cache.get(key)
        if link is not None and link[EXPIRE] > self.time_func():
            self._bump(link)
            return link[VALUE]
        return default

    def _setitem(self, key, value, timeout=None):
        KEY, VALUE = 2, 3
        cache = self._cache
        expire = self.time_func() + (
            self._default_timeout
            if timeout is None else
            timeout
            )
        link = self._cache.get(key)
        if link:
            link = self._bump(link)
            link[VALUE:] = (value, expire)
        elif self._full:
            link = self._shift(pop=True)
            link[KEY:] = (key, value, expire)
            self._cache[key] = link
        else:
            self._cache[key] = self._insert([None, None, key, value, expire])
            self._full = (len(cache) >= self._maxsize)
        return value

    def _popitem(self, key, default=NOT_FOUND):
        VALUE = 3
        link = self._cache.pop(key, None)
        return self._extract(link)[VALUE] if link else default

    def add(self, key, value, timeout=None):
        with self._lock:
            if key in self._cache:
                return False
            self._setitem(key, value, timeout)
            return True

    def set(self, key, value, timeout=None):
        with self._lock:
            self._setitem(key, value, timeout)
            return True

    def set_many(self, mapping, timeout=None):
        with self._lock:
            for key, value in mapping.items():
                self._setitem(key, value, timeout)
            return True

    def inc(self, key, delta=1):
        VALUE = 3
        with self._lock:
            return self._setitem(key, self._cache.get(key, 0)[VALUE] + delta)

    def dec(self, key, delta=1):
        return self.inc(key, delta=-delta)

    def delete(self, key):
        with self._lock:
            return self._popitem(key) is not NOT_FOUND

    def delete_many(self, *keys):
        with self._lock:
            return NOT_FOUND not in [self._popitem(key) for key in keys]

    def get(self, key):
        with self._lock:
            return self._getitem(key, None)

    def get_dict(self, *keys):
        with self._lock:
            return {key: self._getitem(key, None) for key in keys}

    def get_many(self, *keys):
        with self._lock:
            return [self._getitem(key, None) for key in keys]

    def has(self, key):
        return key in self._cache

    def clear(self):
        '''
        Clear cache.
        '''
        with self._lock:
            self._cache.clear()
            self._full = False
            self._key = None
            return True
