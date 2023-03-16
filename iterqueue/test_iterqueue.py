#!/usr/bin/env python3

import queue
import threading
import time
import unittest

import iterqueue


class TestQueueCompatible(unittest.TestCase):
    '''Test that this is still compatible with the queue.Queue methods'''

    def test_basic_queue(self):
        '''Test that the overriden methods still work in the old fasion'''

        target = iterqueue.Iterqueue()

        # - add a few items
        with self.assertWarns(Warning):
            for i in range(1, 9):
                target.put(i)

        # - remove those items
        for i in range(1, 5):
            self.assertEqual(i, target.get())
        for i in range(5, 9):
            self.assertEqual(i, target.get_nowait())

        # - test that we hit a Queue.Empty got gets
        with self.assertRaises(queue.Empty):
            target.get(block=False)
        with self.assertRaises(queue.Empty):
            target.get_nowait()


class TestProducerSide(unittest.TestCase):
    '''Test the producer side methods work'''

    def test_pre_fill(self):
        '''Test before we open or add any data'''

        target = iterqueue.Iterqueue()

        # - test status and opens
        self.assertEqual(iterqueue.Status.Unstarted, target.status)
        self.assertEqual(0, target.writers)

        # - test that we hit a Queue.Empty got gets
        with self.assertRaises(queue.Empty):
            target.get(block=False)
        with self.assertRaises(queue.Empty):
            target.get_nowait()

    def test_context_manager(self):
        '''Check that the context manager works as expected'''

        target = iterqueue.Iterqueue()
        self.assertEqual(iterqueue.Status.Unstarted, target.status)

        with target:
            # - check on the first writer, then add one
            self.assertEqual(iterqueue.Status.Started, target.status)
            self.assertEqual(1, target.writers)
            target.put(1)

            # - add a second writer and check, then add one
            with target:
                self.assertEqual(iterqueue.Status.Started, target.status)
                self.assertEqual(2, target.writers)
                target.put_nowait(2)
            
            # - back on the first writer, check status and remove an items
            self.assertEqual(iterqueue.Status.Started, target.status)
            self.assertEqual(1, target.writers)

            # - get the two items, and demonstrate one get_nowait raises
            self.assertEqual(1, target.get())
            self.assertEqual(2, target.get())
            with self.assertRaises(queue.Empty):
                target.get_nowait()

            # - add an item
            target.put(3)
        
        # - with all released show we are closed, get_nowait works once and then shows ended
        self.assertEqual(iterqueue.Status.Stopped, target.status)
        self.assertEqual(0, target.writers)

        self.assertEqual(3, target.get())
        with self.assertRaises(StopIteration):
            target.get_nowait()
    
    def test_cancel(self):
        '''Ensure the cancel prevents puts and gets'''

        target = iterqueue.Iterqueue()
        with self.assertWarns(Warning):
            for i in range(1, 4):
                target.put(1)
        
        # - show that it starts out in non-cacneled mode
        self.assertFalse(target.canceled)

        # - cancel the queue
        self.assertFalse(target.canceled)
        target.cancel()
        self.assertEqual(target.status, iterqueue.Status.Canceled)
        self.assertTrue(target.canceled)

        # - show that it errors for put and get
        with self.assertRaises(iterqueue.Canceled):
            target.get()
        with self.assertRaises(iterqueue.Canceled):
            target.get_nowait()
        with self.assertRaises(iterqueue.Canceled):
            target.put(1)
        with self.assertRaises(iterqueue.Canceled):
            target.put_nowait(1)


class TestIter(unittest.TestCase):
    '''Ensure that this works via various methods'''

    target = None
    expected = None

    def setUp(self):
        self.target = iterqueue.Iterqueue()
        self.assertEqual(iterqueue.Status.Unstarted, self.target.status)

        self.expected = [1,2,3]
        with self.target:
            self.assertEqual(iterqueue.Status.Started, self.target.status)
            for i in self.expected:
                self.target.put(i)
        return super().setUp()

    def test_list(self):
        '''Check that the list() methods works'''
        self.assertEqual(iterqueue.Status.Stopped, self.target.status)
        self.assertEqual(self.expected, list(self.target))

    def test_for(self):
        '''Ensure `for` loops work'''
        result = []
        for x in self.target:
            result.append(x)
        self.assertEqual(self.expected, result)

    def test_iter_next(self):
        '''Ensure that iter/next works'''
        result = []
        target_iter = iter(self.target)
        with self.assertRaises(StopIteration):
            while True:
                result.append(next(target_iter))
        self.assertEqual(self.expected, result)
    
    def test_resumable(self):
        '''Demonstrate that exausted queues can have more added, and then removed'''
        for _ in range(5):
            # - exaust the given queue, and prove it empty
            self.assertEqual(self.expected, [x for x in self.target])
            with self.assertRaises(StopIteration):
                self.target.get_nowait()

            # - re-fill it
            with self.target:
                for i in self.expected:
                    self.target.put_nowait(i)


class TestIterNowait(TestIter):

    real_target = None

    def setUp(self):
        self.real_target = iterqueue.Iterqueue()
        self.target = self.real_target.iter_nowait()
        self.assertEqual(iterqueue.Status.Unstarted, self.real_target.status)

        self.expected = [1,2,3]
        with self.real_target:
            self.assertEqual(iterqueue.Status.Started, self.real_target.status)
            for i in self.expected:
                self.real_target.put(i)
        return super().setUp()
    
    def test_resumable(self):
        '''Demonstrate that exausted queues can have more added, and then removed'''
        for _ in range(5):
            # - exaust the given queue, and prove it empty
            self.assertEqual(self.expected, [x for x in self.real_target.iter_nowait()])
            self.assertEqual([], [x for x in self.real_target.iter_nowait()])

            # - re-fill it
            with self.real_target:
                for i in self.expected:
                    self.real_target.put_nowait(i)
            time.sleep(0.1)

class TestThreadedOperations(unittest.TestCase):
    '''Ensure that threaded readers and writers work'''

    def test_threaded_readers(self):
        '''Test that multiple readers is supported'''

        # - setup
        target = iterqueue.Iterqueue()
        self.assertEqual(iterqueue.Status.Unstarted, target.status)
        target_number = 300
        threads = 3
        per_thread = target_number//threads
        with target:
            for i in range(1, target_number + 1):
                target.put(i)
        
        # - fire off the readers to each read an equal number
        results = {}

        def reader(name):
            # note: this works because of the GIL, but... it is a hack
            results[name] = []
            for _ in range(per_thread):
                results[name].append(target.get_nowait())
        
        my_threads = [threading.Thread(target=reader, args=[i,], daemon=True) for i in range(1, threads + 1)]
        [x.start() for x in my_threads]
        [x.join(timeout=5) for x in my_threads]
        self.assertEqual([False for _ in range(threads)], [x.is_alive() for x in my_threads])

        # - ensure we have the correct number of items in the results
        self.assertEqual(threads, len(results))
        self.assertEqual(list(range(1, threads + 1)), sorted(results.keys()))
        for result in results.values():
            self.assertEqual(per_thread, len(result))

        # - if our numbers do not exactly add up, make sure we can remove the remainder
        remaining = target_number - (per_thread * threads)
        for _ in range(remaining):
            target.get_nowait()
        
        # - show that we now end correctly
        with self.assertRaises(StopIteration):
            target.get_nowait()
    
    def test_threaded_writers(self):
        '''Test that mulitple writers is supported'''
        target = iterqueue.Iterqueue()
        self.assertEqual(iterqueue.Status.Unstarted, target.status)

        # - start a the writers
        threads = 3
        items_to_write = 5
        expected = sorted(list(range(1, items_to_write + 1)) * threads)

        def writer():
            with target:
                for i in range(1, items_to_write + 1):
                    target.put(i)
                    time.sleep(0.02)  # make sure threads can intermingle
        
        writers = [threading.Thread(target=writer, daemon=True) for _ in range(threads)]
        [x.start() for x in writers]

        # - read out the contents and compare them
        actual = [x for x in target]
        self.assertEqual(iterqueue.Status.Stopped, target.status, 'This should have closed with the last writer')
        self.assertFalse(target.canceled, 'The queue should not be canceled')
        self.assertEqual(expected, sorted(actual))

    def test_cancel_reader_on_thread(self):
        '''Test that a thread that has blocked on an exausted queue will cancel'''
        target = iterqueue.Iterqueue()
        with target:  # keep this open the whole time
            self.assertEqual(iterqueue.Status.Started, target.status, 'the `with` should open one')

            # - start the reader to block
            def reader():
                for _ in target:
                    pass  # this should block before this
            
            reader_thread = threading.Thread(target=reader, daemon=True)
            reader_thread.start()

            # - prove that the thread is blocked
            reader_thread.join(timeout=0.2)
            self.assertTrue(reader_thread.is_alive())

            # - cancel the queue
            target.cancel()
            self.assertTrue(target.canceled, 'This should show the cancel')
            self.assertEqual(iterqueue.Status.Canceled, target.status, 'This should show the cancel')

            # - show the reader cancels
            reader_thread.join(timeout=2)
            if reader_thread.is_alive():
                self.fail('blocked reader thread did not cancel in 2 seconds')
    
    def test_cancel_threaded_writer(self):
        '''Ensure that writers cancel when prompted'''
        target = iterqueue.Iterqueue()
        with target:  # keep this open the whole time
            def put_writer():
                with target:
                    i = 1
                    try:
                        while True:
                            target.put(i)
                            time.sleep(0.05)
                    except iterqueue.Canceled:
                        return
            
            def put_nowait_writer():
                with target:
                    i = 1
                    try:
                        while True:
                            target.put_nowait(i)
                            time.sleep(0.05)
                    except iterqueue.Canceled:
                        return
            
            # - start the writers
            put_thread = threading.Thread(target=put_writer, daemon=True)
            put_nowait_thread = threading.Thread(target=put_nowait_writer, daemon=True)
            put_thread.start()
            put_nowait_thread.start()

            # - wait a moment, then cancel
            time.sleep(0.5)
            target.cancel()

            # - show that they have canceled
            [x.join(timeout=1) for x in (put_thread, put_nowait_thread)]
            living = []
            if put_thread.is_alive():
                living.append('put')
            if put_nowait_thread.is_alive():
                living.append('put_nowait')
            if living:
                self.fail('Thread(s) still alive: %s', ', '.join(living))


if __name__ == '__main__':
    unittest.main()
