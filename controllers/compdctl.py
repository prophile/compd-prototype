#!/usr/bin/env python
import functools, redis, json
import sys
from itertools import izip_longest
from copy import copy
from parsedatetime.parsedatetime import Calendar

r = redis.StrictRedis()
subcommands = {}

def send_redis_command(command, **kwargs):
    cp = copy(kwargs)
    cp['command'] = command
    encoded = json.dumps(cp)
    r.publish('comp.command', encoded)

def time_out(length, callback):
    import threading
    timeout = threading.Thread(target = callback)
    timeout.name = "timeout thread"
    timeout.daemon = True
    timeout.start()
    timeout.join(length)
    return timeout.is_alive()

def subcommand(fn):
    subcommands[fn.__name__.replace('_', '-')] = fn
    return fn

def invoke(command, args):
    subcommands[command](*args)

@subcommand
def screen_redraw():
    send_redis_command('screen-redraw')

@subcommand
def screen_add(id, flavour, zone = None):
    flavour = flavour.upper()
    if zone is not None:
        send_redis_command('screen-add', id=int(id), flavour=flavour, zone=zone)
    else:
        send_redis_command('screen-add', id=int(id), flavour=flavour)

@subcommand
def screen_del(id):
    send_redis_command('screen-del', id=int(id))

@subcommand
def screen_override(id):
    message = sys.stdin.read()
    send_redis_command('screen-override', id=int(id), message=message)

@subcommand
def screen_restore(id):
    send_redis_command('screen-restore', id=int(id))

@subcommand
def panic():
    send_redis_command('panic')

@subcommand
def panic_over():
    send_redis_command('panic-over')

@subcommand
def pause():
    send_redis_command('pause')

@subcommand
def unpause():
    send_redis_command('unpause')

@subcommand
def start_competition():
    send_redis_command('start-competition')

@subcommand
def team_add(tla, name, college = None):
    tla = tla.upper()
    if college:
        send_redis_command('add-team', tla=tla, name=name, college=college)
    else:
        send_redis_command('add-team', tla=tla, name=name)

@subcommand
def team_del(tla):
    tla = tla.upper()
    send_redis_command('remove_team', tla=tla)

@subcommand
def team_set_name(tla, name):
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, name=name)

@subcommand
def team_set_college(tla, college):
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, college=college)

@subcommand
def team_set_info(tla):
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, info=sys.stdin.read())

@subcommand
def team_set_notes(tla):
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, notes=sys.stdin.read())

@subcommand
def team_disqualify(tla):
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, disqualified=True)

@subcommand
def team_undisqualify(tla):
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, disqualified=False)

@subcommand
def team_get(tla):
    tla = tla.upper()
    name = r.get('teams.{0}.name'.format(tla))
    info = r.get('teams.{0}.info'.format(tla))
    notes = r.get('teams.{0}.notes'.format(tla))
    disqualified = r.get('teams.{0}.disqualified'.format(tla)) == 'true'
    college = r.get('teams.{0}.college'.format(tla))
    print '{0}: {1}'.format(tla, name)
    if college:
        print college
    if disqualified:
        print '** DISQUALIFIED **'
    if info.strip():
        print ' --- INFO ---'
        print info.strip()
    if notes.strip():
        print ' --- NOTES ---'
        print notes.strip()

@subcommand
def team_list():
    keys = r.keys('teams.*.name')
    for key in keys:
        print '{0}: {1}'.format(key.split('.')[1], r.get(key))

@subcommand
def tinker():
    send_redis_command('tinker')

@subcommand
def briefing():
    send_redis_command('briefing')

@subcommand
def shutdown():
    r.shutdown()

@subcommand
def state():
    gstate = r.get('comp.state.global')
    mstate = r.get('comp.state.match')
    tstate = r.get('comp.state.tinker') == 'true'
    astate = r.get('comp.state.arena')
    print 'Global state: {0}'.format(gstate)
    if gstate == 'MATCH':
        print ' Match state: {0}'.format(mstate)
    if gstate == 'DOWNTIME':
        print 'Tinker state: {0}'.format('TINKER' if tstate else 'BRIEFING')
    print ' Arena state: {0}'.format(astate)

@subcommand
def snoop():
    ps = r.pubsub()
    ps.subscribe('comp.command')
    for command in ps.listen():
        decoded = json.loads(command["data"])
        print decoded["command"]
        del decoded["command"]
        for k, v in decoded.iteritems():
            print "\t{0} = {1}".format(k, v)

@subcommand
def controller_status():
    ps = r.pubsub()
    ps.psubscribe('controller.*.heartbeat')
    detected_controllers = set()
    def background():
        for message in ps.listen():
            controller = message["channel"].split('.')[1]
            if controller in detected_controllers:
                break
            detected_controllers.add(controller)
            print "{0}: {1}".format(controller, message["data"])
    if time_out(6, background) and not detected_controllers:
        print "No controllers online"

def parse_time(s):
    # TODO: add a way to schedule for tomorrow, or other days more generally
    import time
    calendar = Calendar()
    time_struct, handled = calendar.parse(s)
    if not handled & 2:
        raise ValueError('could not parse time')
    return int(time.mktime(time_struct))

@subcommand
def match_schedule_league(name, start_time, *teams):
    send_redis_command('schedule-match', name=name, type='LEAGUE', start=parse_time(start_time),
                       teams = map(lambda x: x.upper(), teams))

@subcommand
def match_schedule_showmatch(name, start_time, *teams):
    send_redis_command('schedule-match', name=name, type='SHOWMATCH', start=parse_time(start_time),
                       teams = map(lambda x: x.upper(), teams))

@subcommand
def match_schedule_knockout(name, start_time, stage):
    send_redis_command('schedule-match', name=name, type='SHOWMATCH', start=parse_time(start_time),
                       stage = int(stage))

@subcommand
def match_delay(start_time, by):
    send_redis_command('delay-matches', start=parse_time(start_time), by=int(by))

@subcommand
def match_cancel(name):
    send_redis_command('cancel-match', name=name)

@subcommand
def music_play(uri):
    """Play music directly by URI.

    This will stop the currently playing track, if any, rather than playing
    over the top.

    """
    send_redis_command('music-play', uri=uri)

@subcommand
def music_stop():
    """Stop the currently playing music.

    If there is no music playing, this command has no effect.

    """
    send_redis_command('music-stop')

@subcommand
def music_next():
    """Advance to the next track in the current playlist."""
    send_redis_command('music-next')

@subcommand
def music_add(uri, *playlists):
    """Add a track to one or more playlists.

    If no playlists are specified, the playlist 'default' is assumed.

    """
    if not playlists:
        playlists = ['default']
    for playlist in playlists:
        send_redis_command('music-add', playlist=playlist, uri=uri)

@subcommand
def music_del(uri, *playlists):
    """Remove a track from one or more playlists.

    If no playlists are specified, the playlist 'default' is assumed.

    """
    if not playlists:
        playlists = ['default']
    for playlist in playlists:
        send_redis_command('music-del', playlist=playlist, uri=uri)

@subcommand
def music_playlist(playlist):
    """Select a playlist for music playback.

    The default playlist is called 'default'.

    """
    send_redis_command('music-playlist', playlist=playlist)

@subcommand
def help(*commands):
    """Display a list of commands.

    May, optionally, take a list of specific commands for more detailed help.

    """
    lines = []
    import sys
    invocation = sys.argv[0]
    def out(string, *args, **kwargs):
        if args or kwargs:
            string = string.format(*args, **kwargs)
        lines.extend(string.split('\n'))
    if not commands:
        out('Available commands:')
    import inspect
    def format_docstring(string):
        return inspect.cleandoc(string)
    for command, function in sorted(subcommands.items()):
        if commands and command not in commands:
            continue
        aspec = inspect.getargspec(function)
        args = list(aspec.args)
        if aspec.varargs is not None:
            args.append(aspec.varargs + '...')
        out('{2}{0} {1}', command, ' '.join('[{0}]'.format(a) for a in args), '\t' if not commands else invocation + ' ')
        if commands and function.__doc__:
            import textwrap
            out(format_docstring(function.__doc__))
        if len(commands) == 1:
            out('')
            out('Implementation: ')
            out(inspect.getsource(function))
    if len(lines) <= 20:
        for line in lines:
            print line
    else:
        import tempfile, os
        fp, filename = tempfile.mkstemp()
        os.write(fp, '\n'.join(lines))
        os.fsync(fp)
        os.system('less "{0}"'.format(filename))
        os.close(fp)

try:
    if len(sys.argv) >= 2:
        invoke(sys.argv[1], sys.argv[2:])
    else:
        invoke('help', [])
except KeyboardInterrupt:
    pass

