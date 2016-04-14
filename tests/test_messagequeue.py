from desmod.messagequeue import MessageQueue, MessageQueue2


def test_message_queue(env):
    mq = MessageQueue(env, capacity=1, send_time=10, recv_time=3)

    def producer(msg, wait):
        yield env.timeout(wait)
        yield mq.send(msg)

    def consumer(expected_msg, wait):
        yield env.timeout(wait)
        msg = yield mq.recv()
        assert msg == expected_msg

    env.process(producer('1st', 0))
    env.process(producer('2nd', 1))
    env.process(consumer('1st', 0))
    env.process(consumer('2nd', 1))
    env.run()
    assert env.now == 26  # 10 + 3 + 10 + 3


def test_message_queue2(env):
    mq = MessageQueue2(env, capacity=1, put_time=10, get_time=3)

    def producer(msg, wait):
        yield env.timeout(wait)
        yield mq.put(msg)

    def consumer(expected_msg, wait):
        yield env.timeout(wait)
        msg = yield mq.get()
        assert msg == expected_msg

    env.process(producer('1st', 0))
    env.process(producer('2nd', 1))
    env.process(consumer('1st', 0))
    env.process(consumer('2nd', 1))
    env.run()
    assert env.now == 26  # 10 + 3 + 10 + 3
