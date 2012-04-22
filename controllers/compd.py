from twisted.internet import reactor

from arena import ArenaController
from screens import ScreenController
from state import StateController

if __name__ == "__main__":
    print "Bringing up state controller..."
    state = StateController()
    print "Bringing up arena controller..."
    arena = ArenaController()
    print "Bringing up screen controller..."
    screens = ScreenController()
    print "compd started"
    reactor.run()

