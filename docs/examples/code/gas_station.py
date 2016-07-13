"""Model refueling at several gas stations.

Each gas station has several fuel pumps and a single, shared reservoir. Each
arrving car pumps gas from the reservoir via a fuel pump.

As the gas station's reservoir empties, a request is made to a tanker truck
company to send a truck to refill the reservoir. The tanker company maintains a
fleet of tanker trucks.

This example demonstrates core desmod concepts including:
 - Modeling using Component subclasses
 - The "batteries-included" simulation environment
 - Centralized configuration
 - Logging

"""
from itertools import count, cycle

from desmod.component import Component
from desmod.queue import Queue
from desmod.simulation import simulate
from simpy import Container, Resource


class Top(Component):
    """Every model has a single top-level Component.

    For this gas station model, the top level components are gas stations and a
    tanker truck company.

    """

    def __init__(self, *args, **kwargs):
        super(Top, self).__init__(*args, **kwargs)

        # The simulation configuration is available everywhere via the
        # simulation environment.
        num_gas_stations = self.env.config.get('gas_station.count', 1)

        # Instantiate GasStation components. An index is passed so that each
        # child gas station gets a unique name.
        self.gas_stations = [GasStation(self, index=i)
                             for i in range(num_gas_stations)]

        # There is just one tanker company.
        self.tanker_company = TankerCompany(self)

    def connect_children(self):
        # This function is called during the elaboration phase, i.e. after all
        # of the components have been instantiated, but before the simulation
        # phase.
        for gas_station in self.gas_stations:
            # Each GasStation instance gets a reference to (is connected to)
            # the tanker_company instance. This demonstrates the most
            # abbreviated way to call connect().
            self.connect(gas_station, 'tanker_company')


class TankerCompany(Component):
    """The tanker company owns and dispatches its fleet of tanker trunks."""

    # This base_name is used to build names and scopes of component instances.
    base_name = 'tankerco'

    def __init__(self, *args, **kwargs):
        # Many Component subclasses can simply forward *args and **kwargs to
        # the superclass initializer; although Component subclasses may also
        # have custom positional and keyword arguments.
        super(TankerCompany, self).__init__(*args, **kwargs)
        num_tankers = self.env.config.get('tanker.count', 1)

        # Instantiate the fleet of tanker trucks.
        trucks = [TankerTruck(self, index=i) for i in range(num_tankers)]

        # Trucks are dispatched in a simple round-robin fashion.
        self.trucks_round_robin = cycle(trucks)

    def request_truck(self, gas_station, done_event):
        """Called by gas stations to request a truck to refill its reservior.

        Returns an event that the gas station must yield for.

        """
        truck = next(self.trucks_round_robin)

        # Each component has debug(), info(), warn(), and error() log methods.
        # Log lines are automatically annotated with the simulation time and
        # the scope of the component doing the logging.
        self.info('dispatching {} to {}'.format(truck.name, gas_station.name))
        return truck.dispatch(gas_station, done_event)


class TankerTruck(Component):
    """Tanker trucks carry fuel to gas stations.

    Each tanker truck has a queue of gas stations it must visit. When the
    truck's tank becomes empty, it must go refill itself.

    """
    base_name = 'truck'

    def __init__(self, *args, **kwargs):
        super(TankerTruck, self).__init__(*args, **kwargs)
        self.pump_rate = self.env.config.get('tanker.pump_rate', 10)
        self.avg_travel = self.env.config.get('tanker.travel_time', 600)
        tank_capacity = self.env.config.get('tanker.capacity', 200)
        self.tank = Container(self.env, tank_capacity)

        # This auto_probe() call causes the self.tank Container to be
        # monkey-patched such that whenever it's level changes, the new level
        # is noted in the log.
        self.auto_probe('tank', log={})

        # The parent TankerCompany enqueues instructions to this queue.
        self._instructions = Queue(self.env)

        # Declare a persistant process to be started at simulation-time.
        self.add_process(self._dispatch_loop)

    def dispatch(self, gas_station, done_event):
        """Append dispatch instructions to the truck's queue."""
        return self._instructions.put((gas_station, done_event))

    def _dispatch_loop(self):
        """This is the tanker truck's main behavior. Travel, pump, refill..."""
        while True:
            if not self.tank.level:
                self.info('going for refill')

                # Desmod simulation environments come equipped with a
                # random.Random() instance seeded based on the 'sim.seed'
                # configuration key.
                travel_time = self.env.rand.expovariate(1 / self.avg_travel)
                yield self.env.timeout(travel_time)

                self.info('refilling')
                pump_time = self.tank.capacity / self.pump_rate
                yield self.env.timeout(pump_time)

                yield self.tank.put(self.tank.capacity)
                self.info('refilled {}L in {:.0f}s'.format(
                    self.tank.capacity, pump_time))

            gas_station, done_event = yield self._instructions.get()
            self.info('traveling to {}'.format(gas_station.name))
            travel_time = self.env.rand.expovariate(1 / self.avg_travel)
            yield self.env.timeout(travel_time)
            self.info('arrived at {}'.format(gas_station.name))
            while self.tank.level and (gas_station.reservoir.level <
                                       gas_station.reservoir.capacity):
                yield self.env.timeout(1 / self.pump_rate)
                yield gas_station.reservoir.put(1)
                yield self.tank.get(1)
            self.info('done pumping')
            done_event.succeed()


class GasStation(Component):
    """A gas station has a fuel reservoir shared among several fuel pumps.

    The gas station has a traffic generator process that causes cars to arrive
    to fill up their tanks.

    As the cars fill up, the reservoir's level goes down. When the level goes
    below a critical threshold, the gas station makes a request to the tanker
    company for a tanker truck to refill the reservoir.

    """
    base_name = 'station'

    def __init__(self, *args, **kwargs):
        super(GasStation, self).__init__(*args, **kwargs)
        config = self.env.config
        self.add_connections('tanker_company')
        self.arrival_interval = config.get('gas_station.arrival_interval', 60)

        station_capacity = config.get('gas_station.capacity', 200)
        self.reservoir = Container(self.env,
                                   capacity=station_capacity,
                                   init=station_capacity)
        self.auto_probe('reservoir', log={})

        self.threshold_pct = config.get('gas_station.threshold_pct', 10)

        self.pump_rate = config.get('gas_station.pump_rate', 2)
        num_pumps = config.get('gas_station.pumps', 2)
        self.fuel_pumps = Resource(self.env, capacity=num_pumps)
        self.auto_probe('fuel_pumps', log={})

        self.car_capacity = config.get('car.capacity', 50)
        self.car_level_range = config.get('car.level', [5, 25])

        # A gas station has two persistent processes. One to monitor the
        # reservoir level and one that models the arrival of cars at the
        # station. Desmod starts these processes before simulation phase.
        self.add_processes(self._monitor_reservoir, self._traffic_generator)

    @property
    def reservoir_pct(self):
        return self.reservoir.level / self.reservoir.capacity * 100

    def _monitor_reservoir(self):
        """Periodically monitor reservoir level.

        The a request is made to the tanker company when the reservoir falls
        below a critical threshold.

        """
        while True:
            yield self.env.timeout(10)
            if self.reservoir_pct < self.threshold_pct:
                done_event = self.env.event()
                yield self.tanker_company.request_truck(self, done_event)
                yield done_event

    def _traffic_generator(self):
        """Model the sporadic arrival of cars to the gas station."""
        for i in count():
            interval = self.env.rand.expovariate(1 / self.arrival_interval)
            yield self.env.timeout(interval)
            self.env.process(self._car(i))

    def _car(self, i):
        """Model a car transacting fuel."""
        with self.fuel_pumps.request() as pump_req:
            self.info('car{} awaiting pump'.format(i))
            yield pump_req
            self.info('car{} at pump'.format(i))
            car_level = self.env.rand.randint(*self.car_level_range)
            amount = self.car_capacity - car_level
            t0 = self.env.now
            for _ in range(amount):
                yield self.reservoir.get(1)
                yield self.env.timeout(1 / self.pump_rate)
            pump_time = self.env.now - t0
            self.info('car{} pumped {}L in {:.0f}s'.format(
                i, amount, pump_time))


# Desmod uses a plain dictionary to represent the simulation configuration.
# The various 'sim.xxx' keys are reserved for desmod while the remainder are
# application-specific.
config = {
    'car.capacity': 50,
    'car.level': [5, 25],
    'gas_station.capacity': 200,
    'gas_station.count': 3,
    'gas_station.pump_rate': 2,
    'gas_station.pumps': 2,
    'gas_station.arrival_interval': 60,
    'sim.duration': '500 s',
    'sim.log.enable': True,
    'sim.log.file': 'sim.log',
    'sim.log.format': '{level:7} {ts:.3f} {ts_unit}: {scope:<16}:',
    'sim.log.level': 'INFO',
    'sim.result.file': 'results.yaml',
    'sim.seed': 42,
    'sim.timescale': 's',
    'sim.workspace': '.',
    'tanker.capacity': 200,
    'tanker.count': 2,
    'tanker.pump_rate': 10,
    'tanker.travel_time': 100,
}

if __name__ == '__main__':
    # Desmod takes responsibility for instantiating and elaborating the model,
    # thus we only need to pass the configuration dict and the top-level
    # Component class (Top) to simulate().
    simulate(config, Top)
