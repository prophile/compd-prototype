#!/usr/bin/env python
"""This module implements the command-line compdctl tool."""
import sys, time, json
from copy import copy

import redis as redis_module


REDIS = redis_module.StrictRedis()
SUBCOMMANDS = {}

def parse_location(location):
    """Given a user-inputted location, parse it and return a URL safe for
    transmitting to the controllers.

    >>> parse_location('http://www.example.com')
    'http://www.example.com'
    >>> parse_location('http://moo/bees in my eyes')
    'http://moo/bees%20in%20my%20eyes'
    >>> parse_location('/dev/null')
    'file:///dev/null'
    """
    import os.path, urlparse, urllib
    parts = urlparse.urlparse(location)
    if parts.scheme == '': # pylint: disable=E1101
        path = os.path.realpath(location)
        return 'file://{0}'.format(urllib.quote(path if os.path.exists(path)
                                                     else location))
    else:
        return urlparse.urlunparse(urllib.quote(component)
                                   for component in parts)

def send_redis_command(command, **kwargs):
    """Transmit a command to redis.

    Keyword arguments are sent in the command dictionary.
    """
    command_dictionary = copy(kwargs)
    command_dictionary['command'] = command
    encoded_command_dictionary = json.dumps(command_dictionary)
    REDIS.publish('comp.command', encoded_command_dictionary)

def time_out(length, callback):
    """Run a callback, timing out if it takes too long.

    >>> time_out(3.0, lambda: True)
    False
    >>> time_out(3.0, lambda: time.sleep(12))
    True
    >>> time_out(3.0, lambda: time.sleep(1))
    False

    """
    import threading
    checked_thread = threading.Thread(target = callback)
    checked_thread.name = "checked_thread thread"
    checked_thread.daemon = True
    checked_thread.start()
    checked_thread.join(length)
    return checked_thread.is_alive()

def named_subcommand(name):
    """Return a wrapper which installs a subcommand with a given name.

    This is indented to be used as a decorator."""
    def wrapper(handler):
        """Install the command with the name grabbed from the enclosing scope,
        hopefully set in a decorator."""
        SUBCOMMANDS[name] = handler
        return handler
    return wrapper

def subcommand(handler):
    """Install a subcommand.

    Its identifier is taken from the function's __name__, replacing _ with -.
    """
    SUBCOMMANDS[handler.__name__.replace('_', '-')] = handler
    return handler

def invoke(command, args):
    """Invoke a subcommand.

    Arguments are passed in positionally.
    """
    SUBCOMMANDS[command](*args) # pylint: disable=W0142

@subcommand
def unit_tests():
    """Run the compctl unit tests."""
    import doctest
    doctest.testmod()

@subcommand
def screen_redraw():
    """Command all screens to immediately redraw."""
    send_redis_command('screen-redraw')

@subcommand
def screen_flash(screen_id):
    """Flash a given screen."""
    send_redis_command('screen-override', id=int(screen_id), message='<h1 style="color: #990000;">{0}</h1>'.format(screen_id))
    time.sleep(2.5)
    send_redis_command('screen-restore', id=int(screen_id))

@subcommand
def screen_add(screen_id, flavour, zone = None):
    """Add a screen of a given flavour.

    Supported flavours are blank, judge, match-info, layout, zone and clock.

    The 'zone' flavour requires an additional parameter indicating the zone
    of the arena to which the screen is attached.
    """
    flavour = flavour.upper()
    if zone is not None:
        send_redis_command('screen-add', id=int(screen_id), flavour=flavour,
                           zone=zone)
    else:
        send_redis_command('screen-add', id=int(screen_id), flavour=flavour)

@subcommand
def screen_del(screen_id):
    """Remove a screen."""
    send_redis_command('screen-del', id=int(screen_id))

@subcommand
def screen_override(screen_id):
    """Override a screen's display.

    This takes a block of HTML on the standard input with which to override the
    screen's output.
    """
    message = sys.stdin.read()
    send_redis_command('screen-override', id=int(screen_id), message=message)

@subcommand
def screen_restore(screen_id):
    """Restore a screen's content after an override."""
    send_redis_command('screen-restore', id=int(screen_id))

@subcommand
def panic():
    """Sound the alarms and show no-entry signs on all screens."""
    send_redis_command('panic')

def yn_prompt(message):
    """Print out a prompt and ask for a 'yes' or 'no' response.

    This returns a boolean.

    If no value could be interpreted, a ValueError is raised.
    """
    user_line = raw_input(message + ' ')
    if user_line and user_line[0].lower() == 'y':
        return True
    elif user_line and user_line[0].lower() == 'n':
        return False
    else:
        raise ValueError("no idea what you're talking about")

def expect_yes(value):
    """Given a boolean value, indicate whether it was true.

    Whilst this sounds like something out of the daily WTF, its purpose is
    actually slightly saner - it's for the PANIC_OVER_QUESTIONS callbacks.
    """
    return value

def expect_no(value):
    """Given a boolean value, indicate whether it was false.

    Whilst this sounds like something out of the daily WTF, its purpose is
    actually slightly saner - it's for the PANIC_OVER_QUESTIONS callbacks.
    """
    return not value

def killer_sam(value):
    """If value is True indicating a loosed killer, determine key details on
    their identity."""
    if value:
        killer_is_sam = yn_prompt('Is it Sam?')
        if killer_is_sam:
            print "Sam isn't a killer, that's just how he is."
            return True
        else:
            return False
    return True

def removed_body(value):
    """If value is True indicating a death, determine whether the body is still
    festering in the middle of the arena."""
    if value:
        return yn_prompt("OK, did they take away the body?")
    else:
        return True

PANIC_OVER_QUESTIONS = [('Is the arena on fire?', expect_no),
                        ('Are you sure?', expect_yes),
                        ('The arena is on fire, isn\'t it?', expect_no),
                        ('Is anyone dead?', removed_body),
                        ('Is there a killer on the loose?', killer_sam),
                        ('Is everyone still breathing?', expect_yes),
                        ('Has sanity resumed?', expect_yes)]

@subcommand
def panic_over():
    """Cease alarms and panic, after some key sanity checking questions."""
    for question, callback in PANIC_OVER_QUESTIONS:
        selection = yn_prompt(question)
        if not callback(selection):
            print "Then the panic ain't over."
            sys.exit(0)
    panic_over_stall_for_time()
    send_redis_command('panic-over')
    print "OK"

def panic_over_stall_for_time():
    """Configure important configuration. This is not at all to give people an
    opportunity to control-C after panic-over."""
    print "Recalibrating flanges..."
    time.sleep(3)
    print "Configuring splines..."
    time.sleep(2)
    print "Computing bee coefficient..."
    time.sleep(3)
    print "Patching quilt..."
    time.sleep(2)
    print "Initialising flux capacitor..."
    time.sleep(3)

@subcommand
def pause():
    """Pause competition time."""
    send_redis_command('pause')

@subcommand
def unpause():
    """Resume competition time after a previous pause."""
    send_redis_command('unpause')

@subcommand
def start_competition():
    """Trigger the start of festivities."""
    send_redis_command('start-competition')

@subcommand
def team_add(tla, name, college = None):
    """Add a team to the roster.

    If the college is not specified, we assume that the college and name are
    one and the same.
    """
    tla = tla.upper()
    if college:
        send_redis_command('add-team', tla=tla, name=name, college=college)
    else:
        send_redis_command('add-team', tla=tla, name=name)

@subcommand
def team_del(tla):
    """Remove a team from the roster."""
    tla = tla.upper()
    send_redis_command('remove_team', tla=tla)

@subcommand
def team_set_name(tla, name):
    """Set a team's name.

    This is the name which the team themselves select rather than the name of
    the college to which they are attached.
    """
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, name=name)

@subcommand
def team_set_college(tla, college):
    """Set a team's college."""
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, college=college)

@subcommand
def team_set_info(tla):
    """Set a team's 'info' block.

    This block of information contains a team's own written biography and
    information.
    """
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, info=sys.stdin.read())

@subcommand
def team_set_notes(tla):
    """Set a team's 'notes' block.

    This block is for Blueshirt use to store interesting facts and/or relevant
    history about a team.
    """
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, notes=sys.stdin.read())

@subcommand
def team_disqualify(tla):
    """Mark a team as disqualified.

    This does not necessary mean due to any kind of misbehaviour, just that
    they should not be included in the league table and should not be scheduled
    for knockout or league matches.
    """
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, disqualified=True)

@subcommand
def team_undisqualify(tla):
    """Remove the disqualification status on a team."""
    tla = tla.upper()
    send_redis_command('update-team', tla=tla, disqualified=False)

@subcommand
def team_get(tla):
    """Print out all the relevant information on a team."""
    tla = tla.upper()
    name = REDIS.get('teams.{0}.name'.format(tla))
    info = REDIS.get('teams.{0}.info'.format(tla))
    notes = REDIS.get('teams.{0}.notes'.format(tla))
    disqualified = REDIS.get('teams.{0}.disqualified'.format(tla)) == 'true'
    college = REDIS.get('teams.{0}.college'.format(tla))
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
    """Give a list of teams, by TLA and name."""
    keys = REDIS.keys('teams.*.name')
    for key in keys:
        print '{0}: {1}'.format(key.split('.')[1], REDIS.get(key))

@subcommand
def tinker():
    """Switch to tinker time.

    During downtime, this means entry to the arena is permitted so competitors
    can fiddle with their robots.
    """
    send_redis_command('tinker')

@subcommand
def briefing():
    """Switch to briefing time.

    During downtime, this means entry to the arena is forbidden.
    """
    send_redis_command('briefing')

@subcommand
def shutdown():
    """Shut down compd."""
    # We just shut down the redis server, everything else follows naturally
    # from that.
    REDIS.shutdown()

@subcommand
def state():
    """Print out the current overall state of the competition."""
    gstate = REDIS.get('comp.state.global')
    mstate = REDIS.get('comp.state.match')
    tstate = REDIS.get('comp.state.tinker') == 'true'
    astate = REDIS.get('comp.state.arena')
    print 'Global state: {0}'.format(gstate)
    if gstate == 'MATCH':
        print ' Match state: {0}'.format(mstate)
    if gstate == 'DOWNTIME':
        print 'Tinker state: {0}'.format('TINKER' if tstate else 'BRIEFING')
    print ' Arena state: {0}'.format(astate)

@subcommand
def snoop():
    """Block and print out compd commands as other instances send them."""
    pubsub = REDIS.pubsub()
    pubsub.subscribe('comp.command')
    for command in pubsub.listen():
        decoded = json.loads(command["data"])
        print decoded["command"]
        del decoded["command"]
        for argument_key, argument_value in decoded.iteritems():
            print "\t{0} = {1}".format(argument_key, argument_value)

@subcommand
def controller_status():
    """Check the status of the various different compd controllers.

    This in fact listens for the heartbeats and prints out the status
    information attached.
    """
    pubsub = REDIS.pubsub()
    pubsub.psubscribe('controller.*.heartbeat')
    detected_controllers = set()
    def background():
        """Block on the heartbeat channels, printing out statuses as they
        arrive.

        We return when we get a duplicate.
        """
        for message in pubsub.listen():
            controller = message["channel"].split('.')[1]
            if controller in detected_controllers:
                break
            detected_controllers.add(controller)
            print "{0}: {1}".format(controller, message["data"])
    if time_out(6, background) and not detected_controllers:
        print "No controllers online"

def parse_time(time_string):
    """Parse a relative time."""
    from parsedatetime.parsedatetime import Calendar
    calendar = Calendar()
    time_struct, handled = calendar.parse(time_string)
    if not handled & 2:
        raise ValueError('could not parse time')
    return int(time.mktime(time_struct))

@subcommand
def match_schedule_league(name, start_time, *teams):
    """Schedule a league match."""
    send_redis_command('schedule-match', name=name, type='LEAGUE',
                       start=parse_time(start_time),
                       teams = [tla.upper() for tla in teams])

@subcommand
def match_schedule_showmatch(name, start_time, *teams):
    """Schedule a showmatch."""
    send_redis_command('schedule-match', name=name, type='SHOWMATCH',
                       start=parse_time(start_time),
                       teams = [tla.upper() for tla in teams])

@subcommand
def match_schedule_knockout(name, start_time, stage):
    """Schedule a knockout match."""
    send_redis_command('schedule-match', name=name, type='KNOCKOUT',
                       start=parse_time(start_time),
                       stage = int(stage))

@subcommand
def match_delay(start_time, amount):
    """Delay the match(es) starting at a given time by some seconds."""
    send_redis_command('delay-matches', start=parse_time(start_time),
                       amount=int(amount))

@subcommand
def match_cancel(name):
    """Cancel a given match (in the future)."""
    send_redis_command('cancel-match', name=name)

@subcommand
def music_play(uri):
    """Play music directly by URI.

    This will stop the currently playing track, if any, rather than playing
    over the top.

    """
    send_redis_command('music-play', uri=parse_location(uri))

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

    If no playlists are specified, the playlists 'match' and 'downtime' are
    assumed.

    """
    if not playlists:
        playlists = ['default']
    for playlist in playlists:
        send_redis_command('music-add', playlist=playlist,
                           uri=parse_location(uri))

@subcommand
def music_del(uri, *playlists):
    """Remove a track from one or more playlists.

    If no playlists are specified, the playlists 'match' and 'downtime' are
    assumed.

    """
    if not playlists:
        playlists = ['default']
    for playlist in playlists:
        send_redis_command('music-del', playlist=playlist,
                           uri=parse_location(uri))

@subcommand
def music_playlist(playlist):
    """Select a playlist for music playback.

    The special playlist 'auto' will resolve to either 'match' or 'downtime'
    depending on the state at time of play.

    """
    send_redis_command('music-playlist', playlist=playlist)

@subcommand
def music_history():
    """Get the music history."""
    tracks = REDIS.lrange('music.history', 0, -1)
    for track in tracks:
        start_time, uri = track.split(' ', 1)
        time_string = time.strftime('%A %H:%M',
                                    time.localtime(float(start_time)))
        desc = REDIS.hget('music.descriptions', uri)
        if not desc:
            desc = uri
        print time_string, desc

@subcommand
def sound_effect(effect):
    """Play a sound effect."""
    send_redis_command('sound-effect', effect=effect)

@named_subcommand("help")
def interactive_help(*commands):
    """Display a list of commands.

    May, optionally, take a list of specific commands for more detailed help.

    """
    lines = []
    invocation = sys.argv[0]
    action = "specific" if commands else "list"
    def out(string, *args, **kwargs):
        """Print out a line of help text.

        If args or kwargs are provided, they are used arguments to
        string.format.
        """
        if args or kwargs:
            string = string.format(*args, **kwargs)
        lines.extend(string.split('\n'))
    if action == "list":
        out('Available commands:')
    import inspect
    format_docstring = inspect.cleandoc
    for command, function in sorted(SUBCOMMANDS.items()):
        if action == "specific" and command not in commands:
            continue
        aspec = inspect.getargspec(function)
        args = list(aspec.args)
        if aspec.varargs is not None:
            args.append(aspec.varargs + '...')
        out('{2}{0} {1}', command, ' '.join('[{0}]'.format(a) for a in args),
            '\t' if action == "list" else invocation + ' ')
        if action == "specific" and function.__doc__:
            out(format_docstring(function.__doc__))
        if len(commands) == 1:
            from source_dump import format_source
            out('')
            out('Implementation: ')
            out(format_source(function))
    view_text(lines)

VIEW_TEXT_PAGER_THRESHOLD = 20

def view_text(lines):
    """View a block of text in the console.

    If it is fewer than or equal two twenty lines long, this simply displays it
    as-is, otherwise it invokes a pager.
    """
    if len(lines) <= VIEW_TEXT_PAGER_THRESHOLD:
        for line in lines:
            print line
    else:
        import tempfile, os
        file_handle, filename = tempfile.mkstemp()
        os.write(file_handle, '\n'.join(lines))
        os.fsync(file_handle)
        os.system('less -rf "{0}"'.format(filename))
        os.close(file_handle)

def main(args):
    """Run the main program."""
    try:
        if len(args) > 0:
            invoke(args[0], args[1:])
        else:
            invoke('help', [])
    except KeyboardInterrupt:
        pass
    except redis_module.exceptions.ConnectionError:
        print "compd is down"
        sys.exit(1)

if __name__ == "__main__":
    main(sys.argv[1:])

