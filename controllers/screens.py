import redis
from collections import defaultdict
import re, json
from controller import Controller
from controller import ENTER_TIME, BOOT_TIME, LIVE_TIME, SETTLE_TIME
from controller import FULL_MATCH_INTERVAL, PRE_START_INTERVAL, POST_START_INTERVAL
from twisted.internet import reactor, task
from twisted.web import server, resource, static, error
import random

class Screen(object):
    def __init__(self, controller, id):
        self.controller = controller
        self.id = id

    def _get_override(self):
        return self.controller.r.get('screens.{0}.override'.format(self.id))

    def _set_override(self, value):
        self.controller.r.set('screens.{0}.override'.format(self.id), value)

    def _del_override(self):
        self.controller.r.delete('screens.{0}.override'.format(self.id))

    def _get_flavour(self):
        flavour = self.controller.r.get('screens.{0}.flavour'.format(self.id))
        return flavour if flavour is not None else 'UNINITIALISED'

    def _set_flavour(self, value):
        if value == 'UNINITIALISED':
            self.controller.r.delete('screens.{0}.flavour'.format(self.id))
            self.controller.r.delete('screens.{0}.zone'.format(self.id))
            self.controller.r.delete('screens.{0}.override'.format(self.id))
        else:
            self.controller.r.set('screens.{0}.flavour'.format(self.id), value)

    def _get_zone(self):
        zone = self.controller.r.get('screens.{0}.zone'.format(self.id))
        return int(zone) if zone is not None else None

    def _set_zone(self, value):
        if value is None:
            self.controller.r.delete('screens.{0}.zone'.format(self.id))
        else:
            self.controller.r.set('screens.{0}.zone'.format(self.id),
                                  str(value))

    override = property(_get_override,
                        _set_override,
                        _del_override)
    flavour = property(_get_flavour,
                       _set_flavour)
    zone = property(_get_zone,
                    _set_zone)

def match_time(controller, match):
    start = int(controller.r.get('match.schedule.{0}.start'.format(match)))
    offset = controller.competition_time - start
    if 0 <= offset <= LIVE_TIME:
        return '{0}:{1:02d}'.format(offset // 60, offset % 60)
    elif offset > LIVE_TIME:
        return '{0}:{1:02d}'.format(LIVE_TIME // 60, LIVE_TIME % 60)
    elif offset > -60:
        return '{0}'.format(-offset)
    else:
        return ''

class Content(object):
    def __init__(self):
        self.controller = None

    def content(self, screen):
        raise NotImplemented

    def action_for_event(self, event):
        return None

class UninitialisedContent(Content):
    def content(self, screen):
        return '<h1>{0}</h1>'.format(screen.id)

class OverriddenContent(Content):
    def content(self, screen):
        return '<div id="override_message">{0}</span>'.format(screen.override)

class NoEntryContent(Content):
    def content(self, screen):
        return '<div style="text-align: center; width: 100%; margin-left: auto; margin-right: auto;"><object type="image/svg+xml" data="images/no-entry.svg" style="width: 420px; height: 420px;" alt="NO ENTRY"></object>'

class BlankContent(Content):
    def content(self, screen):
        return ''

class ClockContent(Content):
    def clock_display(self):
        import time
        return '<h2 style="font-family: fixed-width; left: -1em">{0}</h2><!-- <br><small>Competition time: {1}</small> -->'.format(time.strftime('%H:%M:%S'), self.controller.competition_time)

    def update(self, screen):
        return {'clock': self.clock_display()}

    def content(self, screen):
        return '<div id="clock">{0}</div>'.format(self.clock_display())

    def action_for_event(self, event):
        if event == 'heartbeat':
            return self.update

class NextMatchContent(Content):
    def content(self, screen):
        for i in xrange(1, 12):
            next_match, _ = self.controller.match_at_competition_time(self.controller.competition_time + FULL_MATCH_INTERVAL*i)
            if next_match is not None:
                import time
                teams = self.controller.r.lrange("match.schedule.{0}.teams".format(next_match), 0, -1)
                start = self.controller.r.get("match.schedule.{0}.start".format(next_match))
                team_names = [self.controller.r.get("teams.{0}.name".format(team)) for team in teams]
                start_rt = self.controller.competition_time_to_real_time(int(start))
                start_str = time.strftime('%H:%M:%S', time.localtime(start_rt))
                return '<div style="margin-top: 6em; margin-bottom: 3em;"><strong style="font-size: 5em;">Up Next</strong></div> <strong style="font-size: x-large;">{0}</strong><br><h4>{1}</h4>'.format('<br>'.join(team_names), start_str)
        return '<h1>Arena</h1>'

    def action_for_event(self, event):
        if event in ('team', 'schedule', 'offset'):
            return self.content

class LayoutContent(Content):
    def content(self, screen):
        import base64
        match = self.controller.r.get('match.current')
        if match is None:
            return '?'
        state = self.controller.r.get('comp.state.match')
        teams = self.controller.r.lrange("match.schedule.{0}.teams".format(match), 0, -1)
        with open('images/layout.svg') as f:
            layout_template = f.read()
        layout_text = layout_template.format(Z0 = teams[0],
                                             Z1 = teams[1],
                                             Z2 = teams[2],
                                             Z3 = teams[3])
        data_uri = 'data:image/svg+xml;charset=UTF-8;base64,{0}'.format(base64.b64encode(layout_text))
        return '<div style="text-align: center; width: 100%; margin-left: auto; margin-right: auto;"><object type="image/svg+xml" data="{0}" style="width: 420px; height: 420px;" alt="pony"></object>'.format(data_uri)

    def action_for_event(self, event):
        if event in ('team', 'schedule'):
            return self.content

class ZoneContent(Content):
    def content(self, screen):
        match = self.controller.r.get('match.current')
        if match is None:
            return '?'
        team = self.controller.r.lindex("match.schedule.{0}.teams".format(match), screen.zone)
        name = self.controller.r.get("teams.{0}.name".format(team))
        time = match_time(self.controller, match)
        return '<h2>{0}</h2><h3 id="time">{1}</h3>'.format(name, time)

    def update(self, screen):
        match = self.controller.r.get('match.current')
        if match is None:
            return {}
        return {'time': match_time(self.controller, match)}

    def action_for_event(self, event):
        if event == 'team':
            return self.content
        elif event in ('heartbeat', 'score'):
            return self.update

class InfoContent(Content):
    def content(self, screen):
        import time
        # TODO: add league
        match_keys = self.controller.r.keys('match.schedule.*.start')
        match_starts = {}
        for key in match_keys:
            match = key.split('.')[2]
            match_starts[self.controller.competition_time_to_real_time(int(self.controller.r.get(key)))] = match
        rt = time.time()
        sched = '<div width="100%" height="100%"><table>'
        sched += '<col style="width: 8em; font-size: x-large;">'
        sched += '<col style="width: 20em; font-size: x-large;">'
        sched += '<tr><th>Time</th><th>Teams</th></tr>'
        for t, match in sorted(match_starts.items()):
            teams = self.controller.r.lrange("match.schedule.{0}.teams".format(match), 0, -1)
            if rt - 30*60 < t < rt + 40*60:
                sched += '<tr><td style="color: {2}; font-size: x-large;">{0}</td><td style="color: {2}; font-size: x-large;">{1}</td></tr>'.format(time.strftime('%H:%M:%S', time.localtime(t)), ', '.join(teams), 'black' if t > rt else '#666666')
        sched += '</table></div>'
        return sched

    def action_for_event(self, event):
        if event in ('offset', 'team', 'schedule'):
            return self.content
        elif event == 'heartbeat' and random.random() < 0.05:
            return self.content

class JudgeStatsContent(Content):
    def content(self, screen):
        match = self.controller.r.get('match.current')
        if match is None:
            return '?'
        state = self.controller.r.get('comp.state.match')
        teams = self.controller.r.lrange("match.schedule.{0}.teams".format(match), 0, -1)
        stats = '<h4>Match {0}</h4>'.format(match)
        stats += '<h4>{0} <span id="time">{1}</span></h4><hr>'.format(state, match_time(self.controller, match))
        stats += '<table>'
        stats += '<col style="width: 10em">'
        stats += '<col style="width: 10em;">'
        stats += '<col style="width: 40em;">'
        stats += '<tr><th>Team</th><th>College</th><th>Notes</th></tr>'
        for team in teams:
            name = self.controller.r.get('teams.{0}.name'.format(team))
            if name is None:
                raise ValueError("team {0} does not exist".format(name))
            college = self.controller.r.get('teams.{0}.college'.format(team))
            notes = self.controller.r.get('teams.{0}.notes'.format(team)).strip()
            stats += '<tr><td style="font-weight: bold;">{0}: {1}</td><td>{2}</td><td style="text-align: justify;">{3}</td></tr>'.format(team, name, college, notes)
        stats += '</table>'
        next_match, _ = self.controller.match_at_competition_time(self.controller.competition_time + FULL_MATCH_INTERVAL)
        stats += '<br>Next match: '
        if next_match is None:
            stats += '<strong>none scheduled</strong>'
        else:
            next_teams = self.controller.r.lrange("match.schedule.{0}.teams".format(next_match), 0, -1)
            stats += '<strong>{0}</strong>'.format(' '.join(next_teams))
        return stats

    def update(self, screen):
        match = self.controller.r.get('match.current')
        if match is None:
            return {}
        return {'time': match_time(self.controller, match)}

    def action_for_event(self, event):
        if event in ('team', 'schedule'):
            return self.content
        elif event in ('heartbeat', 'score'):
            return self.update

def content_for_configuration(screen, gstate, astate):
    flavour = screen.flavour
    if screen.override is not None:
        return OverriddenContent
    elif gstate == "FAIL":
        return NoEntryContent
    elif flavour == "UNINITIALISED":
        return UninitialisedContent
    elif flavour == "CLOCK":
        return ClockContent
    elif flavour == "LAYOUT":
        if astate != "OPEN":
            return NoEntryContent
        elif gstate == "DOWNTIME":
            return NextMatchContent
        elif gstate == "MATCH":
            return LayoutContent
    elif flavour == "ZONE":
        if gstate == "DOWNTIME":
            return ClockContent
        elif gstate == "MATCH":
            return ZoneContent
    elif flavour == "JUDGE":
        if gstate == "DOWNTIME":
            return InfoContent
        elif gstate == "MATCH":
            return JudgeStatsContent
    elif flavour == "MATCH-INFO":
        return InfoContent
    elif flavour == "BLANK":
        return BlankContent
    return BlankContent # play it safe, in case something else screwed up here

def action_for_screen(controller, screen, event):
    gstate, mstate, tstate, astate = controller.state
    content_class = content_for_configuration(screen, gstate, astate)
    content = content_class()
    content.controller = controller
    if event is None:
        return content.content
    else:
        return content.action_for_event(event)

class ScreenController(Controller):
    name = "screens"

    def configure(self):
        self.competition_time = 0
        self._screen_connections = defaultdict(lambda: [])
        self._screens = {}
        self._run_http_server()

    def _register_subscriptions(self, ps):
        ps.psubscribe('teams.*')
        for channel in ('comp.heartbeat',
                        'comp.offset_shift',
                        'comp.state',
                        'comp.arena',
                        'comp.kickoff',
                        'match.reschedule',
                        'match.current.scores',
                        'comp.command'):
            ps.subscribe(channel)

    def next_screen_id(self):
        highest_connected = max([0] + self._screens.keys())
        highest_connected += 1
        while self.r.get('screens.{0}.flavour'.format(highest_connected)) is not None:
            highest_connected += 1
        return highest_connected

    def status_message(self):
        return '{0} screen(s) connected'.format(len(self._screen_connections))

    def receive_heartbeat(self, real_time, competition_time):
        self.competition_time = competition_time
        self.trigger_all('heartbeat')

    def handle_channel_message(self, channel, data):
        if channel.startswith('teams.'):
            self.trigger_all('team')
        elif channel == 'comp.offset_shift':
            self.trigger_all('offset')
        elif channel in ('comp.state', 'comp.arena', 'comp.kickoff'):
            self.trigger_all()
        elif channel == 'match.current.scores':
            self.trigger_all('score')
        elif channel == 'match.reschedule':
            self.trigger_all('schedule')

    def command_screen_redraw(self):
        self.trigger_all()

    def command_screen_add(self, id, flavour, zone = None):
        screen = self[id]
        screen.flavour = flavour
        screen.zone = zone
        self.trigger(screen)

    def command_screen_del(self, id):
        screen = self[id]
        del screen.override
        screen.flavour = "UNINITIALISED"
        self.trigger(screen)

    def command_screen_override(self, id, message):
        screen = self[id]
        screen.override = message
        self.trigger(screen)

    def command_screen_restore(self, id):
        screen = self[id]
        del screen.override
        self.trigger(screen)

    @property
    def state(self):
        return (self.r.get('comp.state.global'),
                self.r.get('comp.state.match'),
                self.r.get('comp.state.tinker') == "true",
                self.r.get('comp.state.arena'))

    def _run_http_server(self):
        controller = self

        class IDGetterResource(resource.Resource):
            isLeaf = True
            def render_POST(self, request):
                request.setHeader("Content-type", "text/plain; charset=UTF-8")
                id = controller.next_screen_id()
                controller[id] # create it
                return str(id)

        class EventStreamResource(resource.Resource):
            isLeaf = True
            def __init__(self, screen):
                resource.Resource.__init__(self)
                self.screen = screen

            def render_GET(self, request):
                request.setHeader("Content-type", "text/event-stream")
                controller.add_sse_stream(self.screen, request)
                return server.NOT_DONE_YET

        class EventDirResource(resource.Resource):
            def getChild(self, path, request):
                try:
                    screen = int(path)
                    return EventStreamResource(controller[screen])
                except ValueError:
                    if path == '':
                        return error.NoResource()
                    else:
                        return error.ForbiddenResource()

        class PanicTriggerResource(resource.Resource):
            isLeaf = True

            def render_POST(self, request):
                import json
                controller.r.publish('comp.command', json.dumps({'command': 'panic'}))
                request.setHeader("Content-type", "text/plain; charset=UTF-8")
                return str("OK")

        class BaseResource(resource.Resource):
            def getChild(self, path, request):
                if path == 'images':
                    return static.File('images')
                elif path == 'events':
                    return EventDirResource()
                elif path == 'favicon.ico':
                    return static.File('images/favicon.ico', 'image/vnd.microsoft.icon')
                elif path == 'assets':
                    return static.File('assets')
                elif path == 'id':
                    return IDGetterResource()
                elif path == 'panic':
                    return PanicTriggerResource()
                elif path == '':
                    return static.File('screen.html', 'text/html; charset=UTF-8')
                else:
                    return error.NoResource()

        reactor.listenTCP(8080, server.Site(BaseResource()))

    def update(self, screen, element, content):
        sse_event = "data: {0}\r\n\r\n".format(json.dumps((element, content)))
        for connection in self._screen_connections[screen.id]:
            try:
                connection.write(sse_event)
            except Exception as e: # gotta catch 'em all
                print e
                self._screen_connections[screen.id].remove(connection)
                try:
                    connection.finish()
                except Exception:
                    pass

    def trigger(self, screen, event = None):
        action = action_for_screen(self, screen, event)
        try:
            result = action(screen) if action else None
            if isinstance(result, str):
                self.update(screen, 'content', result)
            elif result is not None:
                for k, v in result.iteritems():
                    self.update(screen, k, v)
        except Exception as e:
            print "Caught exception updating screen {0}".format(screen.id)
            print e

    def add_sse_stream(self, screen, stream):
        self._screen_connections[screen.id].append(stream)
        self.trigger(screen)

    def __getitem__(self, key):
        if key not in self._screens:
            self._screens[key] = Screen(self, key)
        return self._screens[key]

    @property
    def active_screens(self):
        return [self[screen] for screen in self._screen_connections
                    if self._screen_connections[screen]]

    refresh = trigger

    def trigger_all(self, *args, **kwargs):
        for screen in self.active_screens:
            self.trigger(screen, *args, **kwargs)

if __name__ == "__main__":
    controller = ScreenController()
    reactor.run()

