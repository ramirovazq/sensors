import os
import sqlite3

class FifoMemoryQueue(object):
    def __init__(self):
        self._db = []

    def push(self, item):
        if not isinstance(item, bytes):
            raise TypeError('Unsupported type: {}'.format(type(item).__name__))
        self._db.append(item)

    def pop(self):
        self._db.pop()

    def pull(self, batch_size=10):
        return self._db[:batch_size]

    def close(self):
        self._db = []

    def __len__(self):
        return len(self._db)

class FifoDiskQueue(object):
    _create = (
        'CREATE TABLE IF NOT EXISTS fifoqueue '
        '(id INTEGER PRIMARY KEY AUTOINCREMENT, item BLOB)'
    )
    _size = 'SELECT COUNT(*) FROM fifoqueue'
    _push = 'INSERT INTO fifoqueue (item) VALUES (?)'
    _pop = 'SELECT id, item FROM fifoqueue ORDER BY id LIMIT 1'
    _pull = 'SELECT id, item FROM fifoqueue ORDER BY id LIMIT 10'
    _del = 'DELETE FROM fifoqueue WHERE id = ?'

    def __init__(self, path):
        self._path = os.path.abspath(path)
        self._db = sqlite3.Connection(self._path)
        self._db.text_factory = bytes
        with self._db as conn:
            conn.execute(self._create)

    def push(self, item):
        if not isinstance(item, bytes):
            raise TypeError('Unsupported type: {}'.format(type(item).__name__))

        with self._db as conn:
            conn.execute(self._push, (item,))

    def pop(self):
        with self._db as conn:
            for id_, item in conn.execute(self._pop):
                conn.execute(self._del, (id_,))
                return item

    def pull(self):
        with self._db as conn:
            items = list(conn.execute(self._pull))
            for id_, _ in items:
                conn.execute(self._del, (id_,))
            return [item for _, item in items]

    def close(self):
        #if len(self) == 0:
        #    os.remove(self._path)
        self._db.close()

    def __len__(self):
        with self._db as conn:
            return next(conn.execute(self._size))[0]


class LifoDiskQueue(FifoDiskQueue):
    _create = (
        'CREATE TABLE IF NOT EXISTS lifoqueue '
        '(id INTEGER PRIMARY KEY AUTOINCREMENT, item BLOB)'
    )
    _pop = 'SELECT id, item FROM lifoqueue ORDER BY id DESC LIMIT 1'
    _size = 'SELECT COUNT(*) FROM lifoqueue'
    _push = 'INSERT INTO lifoqueue (item) VALUES (?)'
    _del = 'DELETE FROM lifoqueue WHERE id = ?'
