#!/usr/bin/env python3

import enum
import queue
import threading
import time
import warnings


SPIN_TIME = 0.05  # how often do we check if there is still nothing
CANCELED_TEXT = 'Queue is Canceled. This can not be undone'


class Status(enum.Enum):
    '''Status of the Queue'''
    Unstarted = 'Unstarted'
    Started = 'Started'
    Stopped = 'Stopped'
    Canceled = 'Canceled'


class Canceled(StopIteration):
    '''Signals that the queue has been canceled'''


class Iterqueue(queue.Queue):
    '''Subclass of queue.Queue that allows functions as an iterartor'''

    __status = None
    __writers = 0
    __status_lock = None
    __canceled = None

    def __init__(self, *args, **kwargs):
        self.__status_lock = threading.Lock()
        self.__status = Status.Unstarted
        self.__canceled = threading.Event()
        super().__init__(*args, **kwargs)

    @property
    def status(self):
        '''Return the status of the queue'''
        return self.__status

    @property
    def writers(self):
        '''Returns the number of open writers'''
        return self.__writers

    @property
    def canceled(self):
        '''Returns True if this has been canceled, False otherwise'''
        return self.__canceled.is_set()
    
    def cancel(self):
        '''Cancel the queue, stopping put and gets. Not reversable'''
        self.__canceled.set()
        self.__status = Status.Canceled

    # == context manager setup - required for writers
    def __enter__(self):
        with self.__status_lock:
            self.__writers += 1
            if self.__status != Status.Started:
                self.__status = Status.Started
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        with self.__status_lock:
            self.__writers -= 1
            if self.__writers < 1:
                self.__status = Status.Stopped

    # == superclass overrides
    def get(self, block=True, timeout=None):
        # ToDo: input validation
        deadline = time.time() + timeout if block and timeout else None
        while True:
            if self.__status == Status.Canceled:
                raise Canceled(CANCELED_TEXT)
            try:
                return super().get(block=False)
                # note: we need to spin becuase this is not aware of closes or cancels
            except queue.Empty:
                if self.__status == Status.Stopped:
                    raise StopIteration()
                elif deadline and time.time() < deadline:
                    # there is still wait time remaining
                    time.sleep(SPIN_TIME)
                    continue
                elif block and not deadline:
                    # forever block
                    time.sleep(SPIN_TIME)
                    continue
                else:
                    raise

    def get_nowait(self):
        return self.get(block=False)

    def put(self, *args, **kwargs):
        if self.__status == Status.Canceled:
            raise Canceled(CANCELED_TEXT)
        elif self.__status == Status.Unstarted:
            warnings.warn('`put`/`put_nowait` has been called on an Unstarted CloseableQueue')
        return super().put(*args, **kwargs)
    
    def put_nowait(self, item):
        return super().put_nowait(item)

    # == iterable setup
    def __iter__(self):
        return self
    
    def __next__(self):
        return self.get()

    def iter_nowait(self):
        '''Iterate until a queue.Empty, then raise a StopIteration'''
        try:
            while True:
                yield self.get_nowait()
        except Canceled:
            raise
        except StopIteration:
            pass
 
    # == bool setup
    def __bool__(self):
        '''Retuned True if canceled, useful for while loops'''
        return self.canceled
