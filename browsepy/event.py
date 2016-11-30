
import threading
import collections
import warnings
import os.path

import watchdog.observers
import watchdog.events


class Event(list):
    '''
    Event subscription list.

    A list of callable objects. Calling an instance of this will cause a
    call to each item in the list in ascending order by index.

    Usage:
    >>> def f(x):
    ...     print 'f(%s)' % x
    >>> def g(x):
    ...     print 'g(%s)' % x
    >>> e = Event()
    >>> e()
    >>> e.append(f)
    >>> e(123)
    f(123)
    >>> e.remove(f)
    >>> e()
    >>> e += (f, g)
    >>> e(10)
    f(10)
    g(10)
    >>> del e[0]
    >>> e(2)
    g(2)
    '''

    lock_class = threading.Lock
    queue_class = collections.deque

    def __init__(self, iterable=()):
        self._lock = self.lock_class()
        self._queue = self.queue_class()
        super(Event, self).__init__(iterable)

    def __call__(self, *args, **kwargs):
        self._queue.append((args, kwargs))
        while self._queue:
            if self._lock.acquire(blocking=False):
                try:
                    args, kwargs = self._queue.popleft()
                    for f in self:
                        f(*args, **kwargs)
                finally:
                    self._lock.release()
            else:
                break

    def __repr__(self):
        return "Event(%s)" % list.__repr__(self)


class EventManager(collections.defaultdict):
    '''
    Attribute-dict creating :class:`Event` objects on demand.

    Usage:
    >>> def f(x):
    ...     print 'f(%s)' % x
    >>> def g(x):
    ...     print 'g(%s)' % x
    >>> m = EventManager()
    >>> 'e' in m
    False
    >>> m.e.append(f)
    >>> 'e' in m
    True
    >>> m.e(123)
    f(123)
    >>> m.e.remove(f)
    >>> m.e()
    >>> m.e += (f, g)
    >>> m.e(10)
    f(10)
    g(10)
    >>> del m.e[0]
    >>> m.e(2)
    g(2)
    '''
    def __init__(self):
        super(EventManager, self).__init__(Event)

    def __getattr__(self, name):
        return self[name]


class WathdogEventAdapter(object):
    observer_class = watchdog.observers.Observer
    event_class = collections.namedtuple(
        'FSEvent', ('type', 'path', 'source', 'is_directory')
        )
    event_map = {
        watchdog.events.EVENT_TYPE_MOVED: 'fs_move',
        watchdog.events.EVENT_TYPE_DELETED: 'fs_create',
        watchdog.events.EVENT_TYPE_CREATED: 'fs_modify',
        watchdog.events.EVENT_TYPE_MODIFIED: 'fs_remove'
        }
    _observer = None

    def __init__(self, manager):
        self.manager = manager

    def dispatch(self, wevent):
        event = self.event_class(
            self.event_map[wevent.event_type],
            wevent.dest_path if type == 'fs_move' else wevent.src_path,
            wevent.src_path,
            wevent.is_directory
            )
        event_type_specific = '%s_%s' % (
            event.type,
            'file' if event.is_directory else 'directory'
            )
        self.manager['fs_any'](event)
        self.manager[event.type](event)
        self.manager[event_type_specific](event)

    def watch(self, path):
        if not os.path.isdir(path):
            warnings.warn(
                'Path %r is not observable.',
                category=RuntimeWarning,
                stacklevel=2
                )
            return
        observer = self._observer or self.observer_class()
        observer.schedule(self, path, recursive=True)
        if not self._observer:
            observer.start()
            self._observer = observer

    def clear(self):
        observer = self._observer
        if observer:
            observer.unschedule_all()
            observer.stop()
            observer.join()
        self._observer = None
