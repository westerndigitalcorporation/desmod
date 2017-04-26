"""Model grocery store checkout lanes.

A grocery store checkout system is modeled. Each grocery store has one or more
checkout lanes. Each lane has a cashier that scans customers' items. Zero or
more baggers bag items after the cashier scans them. Cashiers will also bag
items if there is no bagger helping at their lane.

Several bagger assignment policies are implemented. This model helps determine
the optimal policy under various conditions. The model is also useful for
estimating bagger, checkout lane, and cashier resources needed for various
customer profiles.

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

from simpy import Container, Resource
from vcd.gtkw import GTKWSave


class Top(Component):
    """The top-level component of the model."""

    def __init__(self, *args, **kwargs):
        super(Top, self).__init__(*args, **kwargs)
        self.customers = Customers(self)
        self.grocery = GroceryStore(self)

    def connect_children(self):
        self.connect(self.customers, 'grocery')

    @classmethod
    def pre_init(cls, env):
        # Compose a GTKWave save file that lays-out the various VCD signals in
        # a meaningful manner. This must be done at pre-init time to allow
        # sim.gtkw.live to work.
        analog_kwargs = {'datafmt': 'dec',
                         'color': 'cycle',
                         'extraflags': ['analog_step']}
        with open(env.config['sim.gtkw.file'], 'w') as gtkw_file:
            gtkw = GTKWSave(gtkw_file)
            gtkw.dumpfile(env.config['sim.vcd.dump_file'], abspath=False)
            gtkw.treeopen('grocery')
            gtkw.signals_width(300)
            gtkw.trace('customers.active', **analog_kwargs)
            for i in range(env.config['grocery.num_lanes']):
                with gtkw.group('Lane{}'.format(i)):
                    scope = 'grocery.lane{}'.format(i)
                    gtkw.trace(scope + '.customer_queue', **analog_kwargs)
                    gtkw.trace(scope + '.feed_belt', **analog_kwargs)
                    gtkw.trace(scope + '.bag_area', **analog_kwargs)
                    gtkw.trace(scope + '.baggers', **analog_kwargs)

    def elab_hook(self):
        # We generate DOT representations of the component hierarchy. It is
        # only after elaboration that the component tree is fully populated and
        # connected, thus generate_dot() is called here in elab_hook().
        generate_dot(self)


class GroceryStore(Component):
    """Model a grocery store with checkout lanes, cashiers, and baggers."""

    base_name = 'grocery'

    def __init__(self, *args, **kwargs):
        super(GroceryStore, self).__init__(*args, **kwargs)
        num_lanes = self.env.config['grocery.num_lanes']
        self.checkout_lanes = [CheckoutLane(self, index=i)
                               for i in range(num_lanes)]

        num_baggers = self.env.config['grocery.num_baggers']
        self.baggers = [Bagger(self, index=i)
                        for i in range(num_baggers)]

    def connect_children(self):
        # The baggers move between checkout lanes depending on bagger.policy,
        # so each bagger must be connected to all of the checkout lanes.
        for bagger in self.baggers:
            self.connect(bagger, 'checkout_lanes')


class CheckoutLane(Component):
    """Model a grocery store checkout lane.

    Each lane has a customer queue which is modeled with a
    :class:`simpy.Resource`. Customers are addressed in a first-come,
    first-serve manner.

    Once a customer reaches the front of the checkout lane's line, they place
    their items on the lane's feed belt. The feed belt is modeled as a
    :class:`desmod.queue.Queue` and has limited capacity for items. That
    capacity is configurable with `checkout.feed_capacity`.

    The checkout lane's cashier takes items from the feed belt, scans them, and
    places them in the lane's bagging area. The bagging area is also modeled as
    a queue with limited capacity.

    Finally, a checkout lane may have zero or more baggers assigned to it. A
    :class:`simpy.Container` is used to keep track of how many baggers are
    present at each lane.

    """

    base_name = 'lane'

    def __init__(self, *args, **kwargs):
        super(CheckoutLane, self).__init__(*args, **kwargs)

        self.cashier = Cashier(self)

        self.customer_queue = Resource(self.env)
        self.auto_probe('customer_queue', trace_queue=True, vcd={'init': 0})

        feed_capacity = self.env.config['checkout.feed_capacity']
        self.feed_belt = Queue(self.env, capacity=feed_capacity)
        self.auto_probe('feed_belt', vcd={})

        bag_area_capacity = self.env.config['checkout.bag_area_capacity']
        self.bag_area = Queue(self.env, capacity=bag_area_capacity)
        self.auto_probe('bag_area', vcd={})

        self.baggers = Container(self.env)
        self.auto_probe('baggers', vcd={})

    def connect_children(self):
        self.connect(self.cashier, 'lane', conn_obj=self)


class Cashier(Component):
    """Model checkout lane cashier.

    A cashier occupies a single checkout lane. They take items from the lane's
    feeder belt, scan the item, and place the item in the lane's bagging area.

    If no bagger personel is present, the cashier will also perform bagging,
    but a cashier cannot scan and bag at the same time.

    """

    base_name = 'cashier'

    def __init__(self, *args, **kwargs):
        super(Cashier, self).__init__(*args, **kwargs)
        self.add_connections('lane')
        self.add_process(self.checkout)

        # Use exponential distribution to model item scan and bag times.
        self.scan_dist = partial(self.env.rand.expovariate,
                                 1 / self.env.config['cashier.scan_time'])

        self.bag_dist = partial(self.env.rand.expovariate,
                                1 / self.env.config['cashier.bag_time'])

    def checkout(self):
        """Cashier checkout behavior."""
        while True:
            if not self.lane.baggers.level and self.lane.bag_area.is_full:
                yield self.env.process(self.bag_items())
            item, done_event = yield self.lane.feed_belt.get()
            yield self.env.timeout(self.scan_dist())
            yield self.lane.bag_area.put((item, done_event))
            if done_event is not None:
                # A customer's final item comes with a done event. The bag area
                # must be emptied between customers.
                yield self.env.process(self.bag_items())

    def bag_items(self):
        while not self.lane.bag_area.is_empty and not self.lane.baggers.level:
            item, done_event = yield self.lane.bag_area.get()
            yield self.env.timeout(self.bag_dist())
            if done_event is not None:
                # Notify the customer that their checkout is complete.
                done_event.succeed()


class Bagger(Component):
    """Model a grocery store bagger employee.

    Baggers take customer items from checkout lane bagging areas and bag them.

    Several policies for how baggers are assigned to checkout lanes can be
    configured with `bagger.policy`.

    """

    base_name = 'bagger'

    def __init__(self, *args, **kwargs):
        super(Bagger, self).__init__(*args, **kwargs)
        self.add_connections('checkout_lanes')
        self.bag_dist = partial(self.env.rand.expovariate,
                                1 / self.env.config['bagger.bag_time'])

        policy = self.env.config['bagger.policy']
        if policy == 'float-aggressive':
            self.add_process(self.policy_float_aggressive)
        elif policy == 'float-lazy':
            self.add_process(self.policy_float_lazy)
        elif policy == 'fixed-lane':
            self.add_process(self.policy_fixed_lane)
        else:
            raise ValueError('invalid bagger.policy {}'.format(policy))

    def policy_float_aggressive(self):
        """Assign bagger to the first lane with any baggable items.

        The bagger floats between checkout lanes. As soon as a lane is
        identified with any baggable items, the bagger assigns to that lane and
        bags until the lane's bag area is empty.

        """
        while True:
            yield self.env.any_of(lane.bag_area.when_any()
                                  for lane in self.checkout_lanes)

            lanes = reversed(sorted(filter(lambda lane: not lane.baggers.level,
                                           self.checkout_lanes),
                                    key=lambda lane: lane.bag_area.size))
            for lane in lanes:
                yield lane.baggers.put(1)
                self.debug('assigned to lane', lane.index)
                yield self.env.process(self.bag_items(lane.bag_area))
                yield lane.baggers.get(1)
                self.debug('leave lane', lane.index)
                break

    def policy_float_lazy(self):
        """Assign bagger to lane with full bagging area.

        The bagger remains idle until he identifies a lane with a full bagging
        area. The bagger bags at that lane until the bagging area is emptied.

        """
        while True:
            yield self.env.any_of(lane.bag_area.when_full()
                                  for lane in self.checkout_lanes)

            for lane in filter(lambda lane: lane.bag_area.is_full,
                               self.checkout_lanes):
                yield lane.baggers.put(1)
                self.debug('assigned to lane', lane.index)
                yield self.env.process(self.bag_items(lane.bag_area))
                yield lane.baggers.get(1)
                self.debug('leave lane', lane.index)
                break

    def policy_fixed_lane(self):
        """Static assignment of bagger to a lane.

        The bagger finds the first lane with no other baggers and stays there.

        """
        _, lane = min((lane.baggers.level, lane)
                      for lane in self.checkout_lanes)
        yield lane.baggers.put(1)
        self.debug('assigned to lane', lane.index)
        while True:
            yield lane.bag_area.when_any()
            yield self.env.process(self.bag_items(lane.bag_area))

    def bag_items(self, bag_area):
        while not bag_area.is_empty:
            item, done_event = yield bag_area.get()
            yield self.env.timeout(self.bag_dist())
            if done_event is not None:
                done_event.succeed()


class Customers(Component):
    """Model customer arrival rate and in-store behavior.

    Each customer's arrival time, number of items, and shopping time is
    determined by configuration.

    A new process is spawned for each customer.

    A "customers" database table captures per-customer checkout times. A
    primary goal for this model is optimizing customer checkout time (latency)
    and throughput.

    """

    base_name = 'customers'

    def __init__(self, *args, **kwargs):
        super(Customers, self).__init__(*args, **kwargs)
        self.add_connections('grocery')
        self.add_process(self.generate_customers)
        self.active = Container(self.env)
        self.auto_probe('active', vcd={})
        if self.env.tracemgr.sqlite_tracer.enabled:
            self.db = self.env.tracemgr.sqlite_tracer.db
            self.db.execute('CREATE TABLE customers '
                            '(cust_id INTEGER PRIMARY KEY,'
                            ' num_items INTEGER,'
                            ' shop_time REAL,'
                            ' checkout_time REAL)')
        else:
            self.db = None

    def generate_customers(self):
        """Generate grocery store customers.

        Various configuration parameters determine the distribution of customer
        arrival times as well as the number of items each customer will shop
        for.

        """
        cust_id = count()
        arrival_interval_dist = partial(
            self.env.rand.expovariate,
            1 / self.env.config['customer.arrival_interval'])
        time_per_item_dist = partial(
            self.env.rand.expovariate,
            1 / self.env.config['customer.time_per_item'])
        num_items_mu = self.env.config['customer.num_items.mu']
        num_items_sigma = self.env.config['customer.num_items.sigma']
        num_items_dist = partial(
            self.env.rand.normalvariate, num_items_mu, num_items_sigma)

        while True:
            num_items = max(1, round(num_items_dist()))
            self.env.process(
                self.customer(
                    next(cust_id),
                    num_items,
                    shop_time=num_items * time_per_item_dist()))
            yield self.env.timeout(arrival_interval_dist())

    def customer(self, cust_id, num_items, shop_time):
        """Grocery store customer behavior."""
        yield self.active.put(1)
        self.debug(cust_id, 'start shopping for', num_items, 'items')
        yield self.env.timeout(shop_time)
        self.debug(cust_id, 'ready to checkout after',
                   timedelta(seconds=shop_time))

        t0 = self.env.now

        lane = sorted(self.grocery.checkout_lanes,
                      key=lambda lane: len(lane.customer_queue.queue))[0]

        with lane.customer_queue.request() as req:
            self.debug('enter queue', lane.index)
            yield req
            for i in range(num_items - 1):
                yield lane.feed_belt.put((i, None))
            checkout_done = self.env.event()
            yield lane.feed_belt.put((num_items - 1, checkout_done))

        yield checkout_done
        checkout_time = self.env.now - t0
        self.debug(cust_id, 'done checking out after',
                   timedelta(seconds=checkout_time))
        yield self.active.get(1)
        if self.db:
            self.db.execute('INSERT INTO customers '
                            '(cust_id, num_items, shop_time, checkout_time) '
                            'VALUES (?,?,?,?)',
                            (cust_id, num_items, shop_time, checkout_time))

    def get_result_hook(self, result):
        if not self.db:
            return
        result['checkout_time_avg'] = self.db.execute(
            'SELECT AVG(checkout_time) FROM customers').fetchone()[0]
        result['checkout_time_min'] = self.db.execute(
            'SELECT MIN(checkout_time) FROM customers').fetchone()[0]
        result['checkout_time_max'] = self.db.execute(
            'SELECT MAX(checkout_time) FROM customers').fetchone()[0]
        result['customers_total'] = self.db.execute(
            'SELECT COUNT() FROM customers').fetchone()[0]
        result['customers_per_hour'] = (result['customers_total'] /
                                        (self.env.time() / 3600))


if __name__ == '__main__':
    config = {
        'bagger.bag_time': 1.5,
        'bagger.policy': 'float-aggressive',
        'cashier.bag_time': 2.0,
        'cashier.scan_time': 2.0,
        'checkout.bag_area_capacity': 15,
        'checkout.feed_capacity': 20,
        'customer.arrival_interval': 60,
        'customer.num_items.mu': 50,
        'customer.num_items.sigma': 10,
        'customer.time_per_item': 30.0,
        'grocery.num_baggers': 1,
        'grocery.num_lanes': 2,
        'sim.db.enable': True,
        'sim.db.persist': False,
        'sim.dot.colorscheme': 'blues5',
        'sim.dot.enable': True,
        'sim.duration': '7200 s',
        'sim.gtkw.file': 'sim.gtkw',
        'sim.gtkw.live': False,
        'sim.log.enable': True,
        'sim.progress.enable': False,
        'sim.result.file': 'result.json',
        'sim.seed': 1234,
        'sim.timescale': 's',
        'sim.vcd.dump_file': 'sim.vcd',
        'sim.vcd.enable': True,
        'sim.vcd.persist': False,
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
