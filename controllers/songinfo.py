FFMPEG_COMMAND = '/usr/local/bin/ffmpeg'

import subprocess, sys, re, urllib, urlparse

if len(sys.argv) <= 1:
    print "Usage: {0} [file]".format(sys.argv[0])
    sys.exit()

track = urllib.unquote(sys.argv[1])

output = subprocess.check_output([FFMPEG_COMMAND, "-i", track, "-y", "-f", "wav", "/dev/null"], stderr=subprocess.STDOUT)
lines = output.split('\n')
artist = None
title = None
for line in lines:
    match = re.match('^\s*(?:ARTIST|artist)\s*:\s*(.+)\s*$', line)
    if match:
        artist = match.group(1)
    match = re.match('^\s*(?:TITLE|title)\s*:\s*(.+)\s*$', line)
    if match:
        title = match.group(1)
    if artist and title:
        break
if not title:
    desc = urlparse.urlparse(track).path.split('/')[-1]
elif not artist:
    desc = title
else:
    desc = '{1} - {0}'.format(title, artist)
print desc

