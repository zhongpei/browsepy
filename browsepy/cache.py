
import time
import threading
import collections

from werkzeug.contrib.cache import BaseCache


NOT_FOUND = object()


class HashTuple(tuple):
    '''
    Tuple object with cached __hash__ and __repr__.
    '''

    def __hash__(self):
        '''
        Self-caching hash method.

        x.__hash__() <==> hash(x)
        '''
        res = tuple.__hash__(self)
        self.__hash__ = lambda x: res
        return res

    def __repr__(self):
        '''
        Self-caching representation method.

        x.__repr__() <==> repr(x)
        '''
        res = (
            '<{0.__class__.__module__}.{0.__class__.__name__} {1} {2}>'
            ).format(self, hash(self), tuple(self))
        self.__repr__ = lambda x: res
        return res


class MemoizeManager(object):
    '''
    Cache manager object exposed via :attr:`cache` of memoized functions (see
    :meth:`BaseCache.memoize`).
    '''
    hashtuple_class = HashTuple
    NOT_CACHED = object()

    def __init__(self, cache):
        self._hits = 0
        self._misses = 0
        self._cache = cache

    @property
    def hits(self):
        '''
        :returns: number of times result was cached
        :rtype: integer
        '''
        return self._hits

    @property
    def misses(self):
        '''
        :returns: number of times result was not cached
        :rtype: integer
        '''
        return self._missses

    @classmethod
    def make_key(cls, args, kwargs, tuple=tuple):
        '''
        Make a cache key from optionally typed positional and keyword arguments

        The key is constructed in a way that is flat as possible rather than
        as a nested structure that would take more memory.

        If there is only a single argument and its data type is known to cache
        its hash value, then that argument is returned without a wrapper.  This
        saves space and improves lookup speed.
        '''
        key_args = tuple([(arg, arg.__class__) for arg in args])
        key_kwargs = tuple([
            (key, value, value.__class__)
            for key, value in sorted(kwargs.items())
            ])
        return cls.hashtuple_class((key_args, key_kwargs))

    def run(self, fnc, *args, **kwargs):
        key = self.make_key(args, kwargs)
        result = self._cache.get(key, self.NOT_CACHED)
        if result is not self.NOT_CACHED:
            self._hits += 1
            return result
        self._misses += 1
        self._cache[key] = result = fnc(*args, **kwargs)
        return result

    def pop(self, *args, **kwargs):
        key = self.make_key(args, kwargs)
        return self._cache.pop(key, None)

    def clear(self):
        '''
        Clear both cache and statistics.
        '''
        self._hits = 0
        self._misses = 0
        self._cache.clear()


class SafeSimpleCache(BaseCache):
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
        '''
        :param fnc:
        :type fnc: collections.abc.Callable
        :param maxsize: optional maximum cache size (defaults to 1024)
        :type maxsize: int
        '''
        self._default_timeout = default_timeout
        self._cache = {}
        self._full = False
        self._maxsize = maxsize
        self._lock = self.lock_class()
        self._lru_key = None

    def _extract(self, link):
        '''
        Pop given link from circular list.
        '''
        PREV, NEXT = 0, 1
        prev = link[PREV]
        next = link[NEXT]
        prev[NEXT] = next
        next[PREV] = prev
        return link

    def _insert(self, link):
        '''
        Set given link as mru.
        '''
        PREV, NEXT = 0, 1
        next = self._cache.get(self._lru_key) if self._cache else link
        prev = next[PREV]
        link[:2] = (prev, next)
        prev[NEXT] = link
        next[PREV] = link
        return link

    def _shift(self, pop=False):
        '''
        Transform oldest into newest and return it.
        '''
        NEXT, KEY = 1, 2
        if pop:
            link = self._cache.pop(self._older_key)
        else:
            link = self._cache[self._older_key]
        self._lru_key = link[NEXT][KEY]
        return link

    def _bump(self, link):
        NEXT, KEY = 1, 2
        if link[KEY] == self._lru_key:
            return self._shift()
        if link[NEXT][KEY] == self._lru_key:
            return link
        return self._insert(self._extract(link))

    def _getitem(self, key, default=NOT_FOUND):
        VALUE, EXPIRE = 3, 4
        link = self._cache.get(key)
        if link is not None and link[EXPIRE] < self.time_func():
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
        link = self._cache.pop(key, default)
        return self._extract(link)[VALUE]

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
        with self._lock:
            return self._setitem(key, self._cache.get(key, 0) + delta)

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
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._full = False
            return True


class MultiCache(BaseCache):
    '''
    Cache object wrapping multiple caches.
    '''
    def __init__(self, backends=None):
        self.backends = [] if backends is None else backends

    def add(self, key, value, timeout=None):
        return all([c.add(key, value, timeout) for c in self.backends])

    def set(self, key, value, timeout=None):
        return all([c.set(key, value, timeout) for c in self.backends])

    def set_many(self, mapping, timeout=None):
        return all([c.set_many(mapping, timeout) for c in self.backends])

    def _sync(self, key, value, results):
        for backend, partial in results.iteritems():
            if partial != value:
                backend.set(key, value)

    def inc(self, key, delta=1):
        results = {c: c.inc(key, delta=delta) for c in self.backends}
        value = results[max(results, key=results.get)]
        self._sync(key, value, results)
        return value

    def dec(self, key, delta=1):
        results = {c: c.dec(key, delta=delta) for c in self.backends}
        value = results[min(results, key=results.get)]
        self._sync(key, value, results)
        return value

    def delete(self, key):
        '''
        Delete key from all caches.

        :param key:
        :type key: string
        :returns wWhether the key existed on any backend and has been deleted.
        :rtype: bool
        '''
        return any([c.delete(key) for c in self.backends])

    def delete_many(self, *keys):
        return any([c.delete_many(*keys) for c in self.backends])

    def get(self, key):
        for backend in self.backends:
            result = backend.get(key)
            if result is not None:
                return result
        return None

    def _getmany(self, keys, ordered=False):
        remaining = set(keys)
        if ordered:
            result = collections.OrderedDict((key, None) for key in keys)
        else:
            result = {key: None for key in keys}
        for backend in self.backends:
            partial = backend.get_dict(*remaining)
            result.update(partial)
            remaining -= {k for k, v in partial.items() if v is not None}
            if not remaining:
                return
        return result

    def get_dict(self, *keys):
        return self._getmany(keys)

    def get_many(self, *keys):
        return list(self._getmany(keys, ordered=True).values())

    def has(self, key):
        return any(c.has(key) for c in self._cache)

    def clear(self):
        return all([c.clear() for c in self.backends])
