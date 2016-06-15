================
``desmod.queue``
================

.. automodule:: desmod.queue

.. autoclass:: Queue
   :members: capacity, is_empty, is_full, peek

   .. automethod:: put(item)
   .. automethod:: get()
   .. automethod:: when_any()
   .. automethod:: when_full()

.. autoclass:: PriorityQueue
   :inherited-members:
   :members:

.. autoclass:: PriorityItem
   :members: priority, item
