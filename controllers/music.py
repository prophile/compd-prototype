from play_track import play_track, play_file
from controller import Controller
from twisted.internet import reactor
import random

class MusicController(Controller):
    name = "music"

    def configure(self):
        self.current_track = None
        self.current_track_cancel = None
        self.playlist = "default"
        self.stopped_for_fail = None
        self.start_on_live = False

    def _register_subscriptions(self, ps):
        ps.subscribe('comp.state')

    def handle_channel_message(self, channel, data):
        if channel == 'comp.state':
            gstate, mstate = data.split(' ')
            if gstate == 'FAIL':
                if self.current_track is not None:
                    self.stopped_for_fail = self.current_track
                    self.stop()
            else:
                if self.stopped_for_fail:
                    self.play(self.stopped_for_fail)
                    self.stopped_for_fail = None
                elif mstate == 'LIVE' and self.start_on_live:
                    self.next()
                    self.start_on_live = False

    def status_message(self):
        if self.current_track:
            track = "playing track {0}".format(self.current_track)
        else:
            track = "no current track"
        return 'running, {0} (on playlist {1})'.format(track, self.playlist)

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

    def play_effect(self, effect):
        play_file('sfx/{0}.flac'.format(effect))

    def playlist_add(self, playlist, uri):
        minimum = min(score for value, score
                          in self.r.zrangebyscore('music.playlist.{0}'.format(playlist),
                                                  0, float('inf'),
                                                  withscores = True))
        self.r.zadd('music.playlist.{0}'.format(playlist),
                    max(0.0, minimum + random.gauss(0.5, 0.3)),
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

