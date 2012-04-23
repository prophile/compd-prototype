from twisted.internet import reactor, protocol, error

from arena import ArenaController
from screens import ScreenController
from state import StateController

SERVER_COMMAND = '/usr/local/bin/redis-server'

def bring_up_controllers():
    print "Bringing up state controller..."
    state = StateController()
    print "Bringing up arena controller..."
    arena = ArenaController()
    print "Bringing up screen controller..."
    screens = ScreenController()
    print "compd started"

def bring_up_redis():
    class RedisProtocol(protocol.ProcessProtocol):
        def processExited(self, status):
            import sys
            if isinstance(status.value, error.ProcessTerminated):
                print "redis server killed: exit {0}".format(status.value.exitCode)
            reactor.stop()

        def received(self, data):
            print data,

        outReceived = received
        errReceived = received

        def connectionMade(self):
            print "\tredis started."
            reactor.callLater(2.8, bring_up_controllers)

    process = RedisProtocol()
    reactor.spawnProcess(process, SERVER_COMMAND, [SERVER_COMMAND, 'redis.conf'])

if __name__ == "__main__":
    print "Bringing up redis server..."
    bring_up_redis()
    reactor.run()

