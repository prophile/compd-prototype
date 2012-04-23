from twisted.internet import reactor, protocol

GSTREAMER_BIN = '/usr/local/bin/gst-launch'

class TrackPlayerProtocol(protocol.ProcessProtocol):
    def __init__(self, on_finished):
        self.chunk_buffer = []
        self.terminated = False
        self.on_finished = on_finished

    def sendChunk(self, chunk):
        if self.terminated:
            raise IOError("process has ended")
        elif self.chunk_buffer is not None:
            self.chunk_buffer.append(chunk)
        else:
            if chunk is not None:
                self.transport.write(chunk)
            else:
                self.transport.closeStdin()

    def processExited(self, status):
        self.terminated = True
        if self.on_finished:
            self.on_finished()

    def connectionMade(self):
        buffer = self.chunk_buffer
        self.chunk_buffer = None
        for chunk in buffer:
            self.sendChunk(chunk)

class TrackDownloaderProtocol(protocol.ProcessProtocol):
    def __init__(self, chunk_handler):
        self.chunk_handler = chunk_handler
        self.terminated = False

    def outReceived(self, data):
        try:
            self.chunk_handler(data)
        except IOError:
            self.closeStdout()

    def outConnectionLost(self):
        try:
            self.chunk_handler(None)
        except IOError:
            pass

    def processExited(self, status):
        self.terminated = True

def play_track(uri, on_finished = None):
    player_protocol = TrackPlayerProtocol(on_finished)
    downloader_protocol = TrackDownloaderProtocol(player_protocol.sendChunk)
    player_transport = reactor.spawnProcess(player_protocol,
                                            GSTREAMER_BIN,
                                            [GSTREAMER_BIN, 'fdsrc',
                                             'fd=0', '!', 'decodebin',
                                             '!', 'audioconvert', '!',
                                             'audioresample', '!',
                                             'autoaudiosink'])
    downloader_transport = reactor.spawnProcess(downloader_protocol,
                                                'curl',
                                                ['curl', '-N', uri])
    def cancel():
        player_protocol.on_finished = None
        player_transport.signalProcess('TERM')
        # just backup cleanup, a little horrible I know
        def clean_download_process():
            if not downloader_protocol.terminated:
                downloader_transport.signalProcess('KILL')
    return cancel

