"""Model grocery store checkout lanes.
"""
from __future__ import division
from argparse import ArgumentParser
from datetime import timedelta
from functools import partial
from itertools import count

from desmod.config import apply_user_overrides, parse_user_factors
from desmod.component import Component
from desmod.dot import generate_dot
from desmod.queue import Queue
from desmod.simulation import simulate, simulate_factors

from simpy import Container
from vcd.gtkw import GTKWSave


class Top(Component):

    def __init__(self, *args, **kwargs):
        super(Top, self).__init__(*args, **kwargs)
        self.customers = Customers(self)
        self.grocery = Grocery(self)

    def connect_children(self):
        self.connect(self.customers, 'grocery')

    @classmethod
    def pre_init(cls, env):
        analog_kwargs = {'datafmt': 'dec',
                         'color': 'cycle',
                         'extraflags': ['analog_step']}
        with open(env.config['sim.gtkw.file'], 'w') as gtkw_file:
            gtkw = GTKWSave(gtkw_file)
            gtkw.dumpfile(env.config['sim.vcd.dump_file'], abspath=False)
            gtkw.trace('customers.active', **analog_kwargs)
            for i in range(env.config['grocery.num_lanes']):
                gtkw.trace('grocery.lane{}.queue'.format(i), **analog_kwargs)

    def elab_hook(self):
        generate_dot(self)


class Customers(Component):

    base_name = 'customers'

    def __init__(self, *args, **kwargs):
        super(Customers, self).__init__(*args, **kwargs)
        self.add_connections('grocery')
        self.add_process(self.generate_customers)
        self.active = Container(self.env)
        self.auto_probe('active', vcd={})

    def generate_customers(self):
        cust_id = count()
        arrival_interval_dist = partial(
            self.env.rand.expovariate,
            1 / self.env.config['customer.arrival_interval'])
        time_per_item_dist = partial(
            self.env.rand.expovariate,
            1 / self.env.config['customer.time_per_item'])
        num_items_dist = partial(
            self.env.rand.expovariate,
            1 / self.env.config['customer.num_items'])

        while True:
            num_items = max(1, round(num_items_dist()))
            self.env.process(
                self.customer(
                    next(cust_id),
                    num_items,
                    shop_time=num_items * time_per_item_dist()))
            yield self.env.timeout(arrival_interval_dist())

    def customer(self, cust_id, num_items, shop_time):
        yield self.active.put(1)
        self.info(cust_id, 'start shopping for', num_items, 'items')
        yield self.env.timeout(shop_time)
        self.info(cust_id, 'ready to checkout after',
                  timedelta(seconds=shop_time))

        t0 = self.env.now
        checkout_done = self.env.event()
        best_lane = min(self.grocery.checkout_lanes)
        yield best_lane.enqueue(num_items, checkout_done)

        self.info(cust_id, 'waiting to checkout')
        yield checkout_done
        checkout_time = timedelta(seconds=self.env.now - t0)
        self.info(cust_id, 'done checking out after', checkout_time)
        yield self.active.get(1)


class Grocery(Component):

    base_name = 'grocery'

    def __init__(self, *args, **kwargs):
        super(Grocery, self).__init__(*args, **kwargs)
        num_lanes = self.env.config['grocery.num_lanes']
        self.checkout_lanes = [CheckoutLane(self, index=i)
                               for i in range(num_lanes)]


class CheckoutLane(Component):

    base_name = 'lane'

    def __init__(self, *args, **kwargs):
        super(CheckoutLane, self).__init__(*args, **kwargs)
        self.queue = Queue(self.env)
        self.auto_probe('queue', vcd={})
        self.add_process(self.checkout)

    def __lt__(self, other):
        return self.queue.size < other.queue.size

    def enqueue(self, num_items, done_event):
        return self.queue.put((num_items, done_event))

    def checkout(self):
        scan_dist = partial(self.env.rand.expovariate,
                            1 / self.env.config['grocery.scan_time'])
        while True:
            num_items, done_event = yield self.queue.get()
            for n in range(num_items):
                yield self.env.timeout(scan_dist())
            done_event.succeed()


if __name__ == '__main__':
    config = {
        'customer.arrival_interval': 60,
        'customer.num_items': 50,
        'customer.time_per_item': 30,
        'grocery.num_lanes': 2,
        'grocery.scan_time': 2,
        'sim.dot.enable': 1,
        'sim.dot.colorscheme': 'blues5',
        'sim.duration': '7200 s',
        'sim.gtkw.file': 'sim.gtkw',
        'sim.gtkw.live': False,
        'sim.log.enable': True,
        'sim.progress.enable': False,
        'sim.result.file': 'result.json',
        'sim.timescale': 's',
        'sim.vcd.enable': True,
        'sim.workspace': 'workspace',
    }

    parser = ArgumentParser()
    parser.add_argument(
        '--set', '-s', nargs=2, metavar=('KEY', 'VALUE'),
        action='append', default=[], dest='config_overrides',
        help='Override config KEY with VALUE expression')
    parser.add_argument(
        '--factor', '-f', nargs=2, metavar=('KEYS', 'VALUES'),
        action='append', default=[], dest='factors',
        help='Add multi-factor VALUES for KEY(S)')
    args = parser.parse_args()
    apply_user_overrides(config, args.config_overrides)
    factors = parse_user_factors(config, args.factors)
    if factors:
        simulate_factors(config, factors, Top)
    else:
        simulate(config, Top)
