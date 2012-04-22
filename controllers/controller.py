import redis, json, threading, time
from twisted.internet import reactor, task

ENTER_TIME = 90
BOOT_TIME = 60
LIVE_TIME = 180
SETTLE_TIME = 30

FULL_MATCH_INTERVAL = ENTER_TIME + BOOT_TIME + LIVE_TIME + SETTLE_TIME
PRE_START_INTERVAL = ENTER_TIME + BOOT_TIME
POST_START_INTERVAL = LIVE_TIME + SETTLE_TIME

class Controller(object):
    def __init__(self):
        self.r = redis.StrictRedis()
        def ps_thread():
            ps = self.r.pubsub()
            self._register_subscriptions(ps)
            ps.subscribe('comp.command')
            for message in ps.listen():
                channel, data = message['channel'], message['data']
                reactor.callFromThread(self._handle_channel_message, channel, data)
            ps.reset()
        thread_ps = threading.Thread(target = ps_thread)
        thread_ps.name = "{0} pub/sub thread".format(self.__class__.__name__)
        thread_ps.daemon = True
        thread_ps.start()
        self.configure()
        heartbeat_task = task.LoopingCall(self._transmit_heartbeat)
        heartbeat_task.start(4.0)

    def _register_subscriptions(self, pubsub):
        pass

    def match_at_competition_time(self, ct):
        keys = self.r.keys('match.schedule.*.start')
        for key in keys:
            match_id = key.split('.')[2]
            start = int(self.r.get(key))
            offset = ct - start
            if offset >= -PRE_START_INTERVAL and offset < POST_START_INTERVAL:
                # this is the match
                if offset < 0:
                    if offset < -BOOT_TIME:
                        state = 'ENTER'
                    else:
                        state = 'BOOT'
                elif offset < LIVE_TIME:
                    state = 'LIVE'
                else:
                    state = 'SETTLE'
                return (match_id, state)
        return (None, 'SETTLE')


    def match_string_at_competition_time(self, ct):
        string = []
        # TODO: restructure this loop
        while True:
            match, state = self.match_at_competition_time(ct)
            if not match:
                ct += FULL_MATCH_INTERVAL
                match, state = self.match_at_competition_time(ct)
                if not match:
                    break
            string.append(match)
            ct += FULL_MATCH_INTERVAL
        return string

    def _handle_channel_message(self, channel, data):
        if channel == 'comp.command':
            command_data = json.loads(data)
            self.command(command_data["command"], command_data)
        elif channel == 'comp.heartbeat':
            self.receive_heartbeat(*map(int, data.split(' ')))
        else:
            self.handle_channel_message(channel, data)

    def handle_channel_message(self, channel, data):
        pass

    def receive_heartbeat(self, real_time, comp_time):
        pass

    def _transmit_heartbeat(self):
        self.r.publish('controller.{0}.heartbeat'.format(self.name),
                       self.status_message())

    def status_message(self):
        return 'running'

    def command(self, command, data):
        method_name = "command_{0}".format(command.replace('-', '_'))
        try:
            method = getattr(self, method_name)
            import inspect
            args = inspect.getargspec(method).args
            kwdict = {}
            for arg in args[1:]:
                if arg.replace("_", "-") in data:
                    kwdict[arg] = data[arg.replace("_", "-")]
            method(**kwdict)
        except AttributeError:
            pass

    def real_time_to_competition_time(self, rt):
        real, comp = map(int, self.r.lindex('comp.sync', -1).split(' '))
        offset = rt - real
        return comp + offset

    def competition_time_to_real_time(self, ct):
        length = self.r.llen('comp.sync')
        for i in xrange(1, length + 1):
            real, comp = map(int, self.r.lindex('comp.sync', -i).split(' '))
            if comp < ct:
                offset = ct - comp
                return real + offset

