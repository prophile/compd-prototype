import time
from controller import Controller
from twisted.internet import reactor, task

def get_real_time():
    return int(time.time())

from controller import ENTER_TIME, BOOT_TIME, LIVE_TIME, SETTLE_TIME
from controller import FULL_MATCH_INTERVAL, PRE_START_INTERVAL, POST_START_INTERVAL

class StateController(Controller):
    name = "state"

    def configure(self):
        self.real_time = get_real_time()
        self.competition_time = 0
        if self.r.get('comp.state.global') is not None:
            self._start_master_heartbeat()

    def status_message(self):
        return 'paused' if self.r.get('comp.pause') is not None else 'running'

    def _start_master_heartbeat(self):
        t = task.LoopingCall(self._master_heartbeat)
        t.start(1.0)

    def _master_heartbeat(self):
        self._update_real_time()
        self._recompute_competition_time()
        self.r.publish('comp.heartbeat',
                       '{0} {1}'.format(self.real_time, self.competition_time))
        if self.r.get('comp.pause') is None:
            actual_match, actual_mstate = self.match_at_competition_time(self.competition_time)
            expected_match = self.r.get('match.current')
            expected_mstate = self.r.get('comp.state.match')
            gstate = self.r.get('comp.state.global')
            if actual_match != expected_match:
                if expected_match:
                    self.r.set('match.schedule.{0}.state'.format(expected_match), 'COMPLETED')
                if actual_match:
                    self.r.set('match.schedule.{0}.state'.format(actual_match), 'IN-PROGRESS')
                    self.r.set('match.current', actual_match)
                    self._set_state('MATCH', actual_mstate)
                else:
                    self.r.delete('match.current')
                    self._set_state('DOWNTIME', 'SETTLE')
            elif actual_mstate != expected_mstate:
                self._set_state('MATCH', actual_mstate)
        else:
            self._warn_offset()

    def _update_real_time(self):
        self.real_time = get_real_time()

    def command_panic(self):
        self.pause()
        self._set_state('FAIL')

    def command_panic_over(self):
        self.unpause()
        if self.r.get('match.current') is not None:
            self._set_state('MATCH')
        else:
            self._set_state('DOWNTIME')

    def pause(self):
        self.r.set('comp.pause', self.competition_time)

    def unpause(self):
        pause_time = self.r.get('comp.pause')
        if pause_time is None:
            return
        self.r.delete('comp.pause')
        self._record_sync(pause_time)

    command_pause = pause
    command_unpause = unpause

    def _record_sync(self, competition_time):
        self.r.rpush('comp.sync', "{0} {1}".format(self.real_time,
                                                   competition_time))
        self._warn_offset()

    def _set_state(self, gstate, mstate = None):
        self.r.set('comp.state.global', gstate)
        if mstate is None:
            mstate = self.r.get('comp.state.match')
        else:
            self.r.set('comp.state.match', mstate)
        self.r.publish('comp.state', '{0} {1}'.format(gstate, mstate))
        print "changing state to: {0}, {1}".format(gstate, mstate)

    def delay_matches(self, ct, by):
        string = self.match_string_at_competition_time(ct)
        for match in string:
            self.r.set('match.schedule.{0}.start'.format(match),
                       str(int(self.r.get('match.schedule.{0}.start'.format(match))) + by))

    def _recompute_competition_time(self):
        pause_time = self.r.get('comp.pause')
        if pause_time is not None:
            self.competition_time = int(pause_time)
        else:
            self.competition_time = self.real_time_to_competition_time(self.real_time)

    def _warn_offset(self):
        self.r.publish('comp.offset_shift', 'trigger')

    def command_start_competition(self):
        print "signalling kickoff..."
        self.r.publish('comp.kickoff', 'trigger')
        print "setting up CT sync records..."
        self.r.delete('comp.sync')
        self._record_sync(0)
        print "configuring state..."
        self.r.set('comp.state.tinker', 'true')
        self._set_state('DOWNTIME', 'SETTLE')
        print "starting master heartbeat..."
        self._start_master_heartbeat()
        print "the competition is now started"

    # team shenanigans
    def command_add_team(self, tla, name, college = None, info = ''):
        self.r.set('teams.{0}.name'.format(tla), name)
        if college is None:
            college = name
        self.r.set('teams.{0}.college'.format(tla), college)
        self.r.set('teams.{0}.info'.format(tla), info)
        self.r.set('teams.{0}.disqualified'.format(tla), 'false')
        self.r.set('teams.{0}.notes'.format(tla), '')
        self.r.publish('teams.{0}'.format(tla), 'new')

    def command_update_team(self, tla, name = None, college = None,
                                  info = None, notes = None, disqualified = False):
        if name:
            self.r.set('teams.{0}.name'.format(tla), name)
        if college:
            self.r.set('teams.{0}.college'.format(tla), college)
        if info is not None:
            self.r.set('teams.{0}.info'.format(tla), info)
        if notes is not None:
            self.r.set('teams.{0}.notes'.format(tla), notes)
        self.r.set('teams.{0}.disqualified'.format(tla), 'true' if disqualified else 'false')
        self.r.publish('teams.{0}'.format(tla), 'updated')

    def command_remove_team(self, tla):
        self.r.delete('teams.{0}.name'.format(tla))
        self.r.delete('teams.{0}.college'.format(tla))
        self.r.delete('teams.{0}.info'.format(tla))
        self.r.delete('teams.{0}.notes'.format(tla))
        self.r.delete('teams.{0}.disqualified'.format(tla))
        self.r.publish('teams.{0}'.format(tla), 'gone')

    def command_schedule_match(self, name, type, start, stage = None, teams = None):
        start_ct = self.real_time_to_competition_time(start)
        if start_ct <= self.competition_time + PRE_START_INTERVAL:
            return
        if self.r.get('match.schedule.{0}.type'.format(name)) is not None:
            return
        previous, _ = self.match_at_competition_time(start_ct)
        if previous is not None:
            prev_start = int(self.r.get('match.schedule.{0}.start'.format(previous)))
            start_ct = prev_start + POST_START_INTERVAL
        self.delay_matches(start_ct, FULL_MATCH_INTERVAL)
        self.r.set('match.schedule.{0}.type'.format(name), type)
        self.r.set('match.schedule.{0}.start'.format(name), start_ct)
        self.r.set('match.schedule.{0}.state'.format(name), 'UPCOMING')
        if stage is not None:
            self.r.set('match.schedule.{0}.stage'.format(name), stage)
        if teams is not None:
            for team in teams:
                self.r.rpush('match.schedule.{0}.teams'.format(name), team)
        self.r.publish('match.reschedule', 'trigger')

    def command_cancel_match(self, name):
        start_ct = int(self.r.get('match.schedule.{0}.start'.format(name)))
        begin_ct = start_ct - PRE_START_INTERVAL
        if begin_ct >= self.competition_time:
            return # do not cancel matches in the past
        self.r.delete('match.schedule.{0}.type'.format(name))
        self.r.delete('match.schedule.{0}.start'.format(name))
        self.r.delete('match.schedule.{0}.state'.format(name))
        self.r.delete('match.schedule.{0}.stage'.format(name))
        self.r.delete('match.schedule.{0}.teams'.format(name))
        # shift matches back to fill the hole
        self.delay_matches(begin_ct, -FULL_MATCH_INTERVAL)
        self.r.publish('match.reschedule', 'trigger')

    def command_delay_matches(self, start, by):
        ct = self.real_time_to_competition_time(start)
        if ct <= self.competition_time:
            return
        self.delay_matches(ct, by)
        self.r.publish('match.reschedule', 'trigger')

if __name__ == "__main__":
    controller = StateController()
    reactor.run()

