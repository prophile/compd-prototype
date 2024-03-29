from play_track import play_track, play_file, discover_song_description
from controller import Controller
from twisted.internet import reactor
import random

class MusicController(Controller):
    name = "music"

    def configure(self):
        self.current_track = None
        self.current_track_cancel = None
        self._playlist = "auto"
        self.stopped_for_fail = None
        self.start_on_live = False
        self.fail_cancel = None
        if self.r.get('comp.state.global') == 'FAIL':
            self.play_fail_klaxon()

    def _register_subscriptions(self, ps):
        ps.subscribe('comp.state')

    def handle_channel_message(self, channel, data):
        if channel == 'comp.state':
            gstate, mstate = data.split(' ')
            if gstate == 'FAIL':
                if self.current_track is not None:
                    self.stopped_for_fail = self.current_track
                    self.stop()
                self.play_fail_klaxon()
            else:
                self.stop_fail_klaxon()
                if self.stopped_for_fail:
                    self.play(self.stopped_for_fail)
                    self.stopped_for_fail = None
                if gstate == 'MATCH':
                    if mstate == 'LIVE':
                        if self.start_on_live:
                            self.next()
                            self.start_on_live = False
                        self.play_effect('match_begin')
                    elif mstate == 'SETTLE':
                        self.play_effect('match_end')


    def _get_playlist(self):
        if self._playlist == 'auto':
            gstate = self.r.get('comp.state.global')
            if gstate == 'MATCH':
                return 'match'
            else:
                return 'downtime'
        else:
            return self._playlist

    def _set_playlist(self, playlist):
        self._playlist = playlist

    playlist = property(fget = _get_playlist, fset = _set_playlist)

    def status_message(self):
        if self.current_track:
            track = "playing track {0}".format(self.description(self.current_track))
        else:
            track = "no current track"
        return 'running, {0} (on playlist {1})'.format(track, self.playlist)

    def _get_description(self, uri):
        return self.r.hget('music.descriptions', uri)

    def description(self, uri):
        desc = self._get_description(uri)
        if desc:
            return desc
        else:
            from urlparse import urlparse
            return urlparse(uri).path.split('/')[-1]

    def play(self, uri):
        self.stop()
        def completed():
            self.current_track = None
            self.current_track_cancel = None
            if self.r.get('comp.state.match') == 'BOOT':
                self.start_on_live = True
            else:
                self.next()
        self.current_track = uri
        self.current_track_cancel = play_track(uri, completed)
        import time
        self.r.rpush('music.history', '{0} {1}'.format(time.time(),
                                                       uri))
        if not self._get_description(uri):
            def got_description(desc):
                self.r.hsetnx('music.descriptions', uri, desc)
            discover_song_description(uri, got_description)

    def stop(self):
        if self.current_track_cancel:
            self.current_track_cancel()
            self.current_track_cancel = None
            self.current_track = None

    def next(self):
        track = self.playlist_pick(self.playlist)
        # pick a track here and play it
        if track is not None:
            self.play(track)

    def play_fail_klaxon(self):
        if self.fail_cancel:
            return
        def play_klaxon():
            import os.path
            self.fail_cancel = play_file('sfx/fail_klaxon.flac', play_klaxon)
        play_klaxon()

    def stop_fail_klaxon(self):
        if self.fail_cancel:
            self.fail_cancel()
            self.fail_cancel = None

    def play_effect(self, effect):
        play_file('sfx/{0}.flac'.format(effect))

    def playlist_add(self, playlist, uri):
        minimum = min(score for value, score
                          in [(0, 0)] +
                             self.r.zrangebyscore('music.playlist.{0}'.format(playlist),
                                                  0, float('inf'),
                                                  withscores = True))
        self.r.zadd('music.playlist.{0}'.format(playlist),
                    minimum + random.random(),
                    uri)

    def playlist_remove(self, playlist, uri):
        self.r.zrem('music.playlist.{0}'.format(playlist), uri)

    def playlist_pick(self, playlist):
        l = self.r.zrangebyscore('music.playlist.{0}'.format(playlist),
                                 0, float('inf'),
                                 start = 0, num = 1)
        if not l:
            return None
        picked = l[0]
        self.r.zincrby('music.playlist.{0}'.format(playlist),
                       picked,
                       1.0 + abs(random.gauss(0.0, 0.5)))
        return picked

    def command_music_play(self, uri):
        self.play(uri)

    def command_music_stop(self):
        self.stop()

    def command_music_next(self):
        self.next()

    def command_music_add(self, playlist, uri):
        self.playlist_add(playlist, uri)

    def command_music_del(self, playlist, uri):
        self.playlist_remove(playlist, uri)

    def command_music_playlist(self, playlist):
        self.playlist = playlist

    def command_sound_effect(self, effect):
        self.play_effect(effect)

if __name__ == "__main__":
    controller = MusicController()
    reactor.run()

