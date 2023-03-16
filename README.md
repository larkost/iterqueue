# iterqueue
A Python Queue subclass that consumers can use as an iterator.

# Introduction

The `Iterqueue` class is a subclass that allows threaded consumers from a Python `Queue`-like object to use it like a iterator, for example with a `for` loop. This requries the concept of an end to the queue, and that requires some change on the producer side of a queue.

The change in this module is to require that producers use the `Queue` as a context (using `with`), and consumers can use it via a `for` statement. A trivial example:

```python
import iterqueue

# create a Queue, and add something to it
target = iterqueue.Iterqueue()
with target:  # this is required, without it the consumer will hang
  target.put(1)

# read out the contents
for item in target:
  print(item)

# here all items have been processed
```

Normally producers and consumers should each be in their own thread, and this class supports multiple simultanious producers and consumers. The consumers can just use it in a `for` loop, while the producers should use it via a `with` statement and when the producers are complete (drop through the `with` statement), and the queue is exausted the consumers will stop (via a `StopIteration`). Canceling in the middle (from consumers, producers, or otherwise) is also supported.