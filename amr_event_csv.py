"""Stream the legacy CSV representation to report parsers without a disk copy."""
import csv
import io
import json
from pathlib import Path

from amr_event_store import EventStore


class EventCSVReader(io.RawIOBase):
    """Bounded binary stream with exactly the explicit event export's columns."""
    def __init__(self, path):
        super().__init__()
        self._chunks = self._csv_chunks(path)
        self._pending = b''
        self._offset = 0

    @staticmethod
    def _csv_chunks(path):
        store = EventStore(path, readonly=True)
        try:
            headers = store.connection.execute("SELECT value FROM metadata WHERE key='report_headers'").fetchone()
            if headers is None:
                raise ValueError('Compact evidence has no report columns')
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=json.loads(headers[0])['steps_csv'], extrasaction='ignore')
            writer.writeheader()
            for row in store.iter_rows():
                writer.writerow(row)
                if stream.tell() >= 64 * 1024:
                    yield stream.getvalue().encode('utf-8')
                    stream.seek(0)
                    stream.truncate(0)
            if stream.tell():
                yield stream.getvalue().encode('utf-8')
        finally:
            store.close()

    def readable(self):
        return True

    def readinto(self, target):
        if self.closed:
            raise ValueError('Read of closed event stream')
        if not len(target):
            return 0
        if self._offset == len(self._pending):
            self._pending = next(self._chunks, b'')
            self._offset = 0
        size = min(len(target), len(self._pending) - self._offset)
        target[:size] = self._pending[self._offset:self._offset + size]
        self._offset += size
        return size

    def close(self):
        if not self.closed:
            self._chunks.close()
            self._pending = b''
        super().close()


def read_event_csv(path, **kwargs):
    """Use pandas' existing CSV parsing and dtype rules for either log format."""
    import pandas as pd
    if Path(path).suffix != '.sqlite':
        return pd.read_csv(path, **kwargs)
    if kwargs.get('chunksize'):
        def chunks():
            with io.BufferedReader(EventCSVReader(path)) as stream:
                with pd.read_csv(stream, **kwargs) as reader:
                    yield from reader
        return chunks()
    with io.BufferedReader(EventCSVReader(path)) as stream:
        return pd.read_csv(stream, **kwargs)
