import time
from controller import Controller
from twisted.internet import reactor, task

from controller import ENTER_TIME, BOOT_TIME, LIVE_TIME, SETTLE_TIME
from controller import FULL_MATCH_INTERVAL, PRE_START_INTERVAL, POST_START_INTERVAL

class ArenaController(Controller):
    name = "arena"

    def configure(self):
        self._update_arena_state()

    def _register_subscriptions(self, ps):
        ps.subscribe('comp.state')

    def handle_channel_message(self, channel, data):
        if channel == 'comp.state':
            gstate, mstate = data.split(' ')
            self._update_arena_state()
            if gstate == 'MATCH':
                cmatch = self.r.get('match.current')
                team_count = self.r.llen('match.schedule.{0}.teams'.format(cmatch))
                if mstate == 'LIVE':
                    for i in xrange(team_count):
                        self.r.rpush('match.schedule.{0}.scores'.format(cmatch), '0')
                    self._transmit_scores()
                elif mstate == 'SETTLE':
                    self._transmit_scores()

    def _transmit_scores(self):
        cmatch = self.r.get('match.current')
        self.r.publish('match.current.scores', ' '.join(str(x) for x in self.r.lrange('match.schedule.{0}.scores'.format(cmatch), 0, -1)))

    def status_message(self):
        return 'running, {0}'.format(self.r.get('comp.state.arena'))

    def command_tinker(self):
        self.r.set('comp.state.tinker', 'true')
        self._update_arena_state()

    def command_briefing(self):
        self.r.set('comp.state.tinker', 'false')
        self._update_arena_state()

    def _update_arena_state(self):
        prev_state = self.r.get('comp.state.arena')
        gstate, mstate, tstate = (self.r.get('comp.state.global'),
                                  self.r.get('comp.state.match'),
                                  self.r.get('comp.state.tinker') == 'true')
        if gstate == 'FAIL':
            next_state = 'HARD-CLOSED'
        elif gstate == 'DOWNTIME':
            next_state = 'OPEN' if tstate else 'SOFT-CLOSED'
        elif gstate == 'MATCH':
            next_state = {'ENTER': 'OPEN',
                          'BOOT': 'SOFT-CLOSED',
                          'LIVE': 'HARD-CLOSED',
                          'SETTLE': 'SOFT-CLOSED'}[mstate]
        else:
            return
        if next_state != prev_state:
            self.r.set('comp.state.arena', next_state)
            self.r.publish('comp.arena', next_state)

if __name__ == "__main__":
    controller = ArenaController()
    reactor.run()

