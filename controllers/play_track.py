from twisted.internet import reactor, protocol, error

GSTREAMER_BIN = '/usr/local/bin/gst-launch'
PRINT_DEBUGGING_OUTPUT = False

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

    def outReceived(self, message):
        if PRINT_DEBUGGING_OUTPUT:
            print message,
    def errReceived(self, message):
        if PRINT_DEBUGGING_OUTPUT:
            print message,

class TrackDownloaderProtocol(protocol.ProcessProtocol):
    def __init__(self, chunk_handler):
        self.chunk_handler = chunk_handler
        self.terminated = False

    def outReceived(self, data):
        try:
            self.chunk_handler(data)
        except IOError:
            self.transport.closeStdout()

    def outConnectionLost(self):
        try:
            self.chunk_handler(None)
        except IOError:
            pass

    def errReceived(self, message):
        if PRINT_DEBUGGING_OUTPUT:
            print message,

    def processExited(self, status):
        self.terminated = True

class SongInfoProtocol(protocol.ProcessProtocol):
    def __init__(self, name_handler, fail_handler):
        self.name_handler = name_handler
        self.fail_handler = fail_handler
        self.name_buffer = ''

    def outReceived(self, data):
        if PRINT_DEBUGGING_OUTPUT:
            print data,
        self.name_buffer += data

    def processEnded(self, status):
        if not isinstance(status.value, error.ProcessTerminated):
            self.name_handler(self.name_buffer.strip())
        else:
            self.fail_handler()
            if PRINT_DEBUGGING_OUTPUT:
                print status

    def errReceived(self, message):
        if PRINT_DEBUGGING_OUTPUT:
            print message,

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
                                                ['curl', '-N', '-L', uri])
    def cancel():
        player_protocol.on_finished = None
        player_transport.signalProcess('TERM')
        # just backup cleanup, a little horrible I know
        def clean_download_process():
            if not downloader_protocol.terminated:
                downloader_transport.signalProcess('KILL')
    return cancel

def play_file(path, on_finished = None):
    import urllib, os.path
    file_uri = 'file://{0}'.format(urllib.quote(os.path.realpath(path)))
    return play_track(file_uri, on_finished)

def discover_song_description(uri, on_found):
    def found(name):
        if PRINT_DEBUGGING_OUTPUT:
            print "{0} is {1}".format(uri, name)
        on_found(name)
    def not_found():
        if PRINT_DEBUGGING_OUTPUT:
            print "failed to discover name for {0}".format(uri)
    info_protocol = SongInfoProtocol(found, not_found)
    reactor.spawnProcess(info_protocol,
                         'python',
                         ['python', 'songinfo.py', uri])

