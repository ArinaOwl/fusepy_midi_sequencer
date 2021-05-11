import errno
import io
import os
import time
from stat import S_IFDIR, S_IFREG

import mido
from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

NOW = time.time()
DIR_MODE = (S_IFDIR | 0o444)
FILE_MODE = (S_IFREG | 0o555)


class Property(dict):
    def __init__(self, st_mode=0o000000, st_nlink=0, st_ctime=0., st_mtime=0., st_atime=0.,
                 st_gid=os.getgid(), st_uid=os.getuid(), st_size=0):
        super().__init__()
        self.st_mode = st_mode
        self.st_nlink = st_nlink
        self.st_ctime = st_ctime
        self.st_mtime = st_mtime
        self.st_atime = st_atime
        self.st_gid = st_gid
        self.st_uid = st_uid
        self.st_size = st_size


class Directory(object):
    def __init__(self, files, directories, properties):
        self.files = files
        self.directories = directories
        self.properties = properties


class File(object):
    def __init__(self, data, properties):
        self.data = data
        self.properties = properties


class MIDISequencer(LoggingMixIn, Operations):

    def __init__(self, path):
        self.fd = 0
        self.mid = mido.MidiFile(path)
        self.filesystem = {'/': Directory(files={}, directories={},
                                          properties=Property(st_mode=DIR_MODE, st_nlink=2,
                                                              st_ctime=NOW, st_mtime=NOW, st_atime=NOW,
                                                              st_gid=os.getgid(), st_uid=os.getuid()))}
        header = "format: {0}\nntrks: {1}".format(self.mid.type, len(self.mid.tracks))
        self.add_file("HEADER.txt", bytes(header, 'utf-8'), self.filesystem['/'], FILE_MODE)
        self.sequencer()

    def sequencer(self):
        mid_format = self.mid.type
        if mid_format == 0:
            # the file contains a single multi-channel track
            fp = io.BytesIO()
            self.mid.save(file=fp)
            self.add_dir("track", self.filesystem['/'], DIR_MODE)
            track = self.mid.tracks[0]
            channels = {}
            ch = 0
            for msg in track:
                if not msg.is_meta:
                    ch = msg.channel
                    if not (ch in channels):
                        channels[ch] = mido.MidiTrack()
                    channels[ch].append(msg)
                else:
                    if msg.type == "channel_prefix":
                        ch = msg.data
                    if not (ch in channels):
                        channels[ch] = mido.MidiTrack()
                    channels[ch].append(msg)
            for ch in channels:
                mid_channel = mido.MidiFile()
                mid_channel.tracks.append(channels[ch])
                fp = io.BytesIO()
                mid_channel.save(file=fp)
                self.add_file("channel{0}.mid".format(ch), fp.getvalue(),
                              self.filesystem['/'].directories["track"], FILE_MODE)

        elif mid_format == 1:
            # the file contains one or more simultaneous tracks (or MIDI outputs) of a sequence
            self.add_dir("tracks", self.filesystem['/'], DIR_MODE)
            for i, track in enumerate(self.mid.tracks):
                mid_track = mido.MidiFile(ticks_per_beat=self.mid.ticks_per_beat)
                mid_track.tracks.append(track)
                mid_track.type = 0
                fp = io.BytesIO()
                mid_track.save(file=fp)
                self.add_file("track{0}.mid".format(i), fp.getvalue(),
                              self.filesystem['/'].directories["tracks"], FILE_MODE)

        else:
            # the file contains one or more sequentially independent single-track patterns
            self.add_dir("tracks", self.filesystem['/'], DIR_MODE)
            for i, track in enumerate(self.mid.tracks):
                self.add_dir("track{0}".format(i), self.filesystem['/'].directories["tracks"], DIR_MODE)
                mid_track = mido.MidiFile(ticks_per_beat=self.mid.ticks_per_beat)
                mid_track.tracks.append(track)
                mid_track.type = 0
                fp = io.BytesIO()
                mid_track.save(file=fp)
                self.add_file("track{0}.mid".format(i), fp.getvalue(),
                              self.filesystem['/'].directories["tracks"], FILE_MODE)
                channels = {}
                ch = 0
                for msg in mid_track:
                    if not msg.is_meta:
                        ch = msg.channel
                        if not (ch in channels):
                            channels[ch] = mido.MidiTrack()
                        channels[ch].append(msg)
                    else:
                        if msg.type == "channel_prefix":
                            ch = msg.data
                        if not (ch in channels):
                            channels[ch] = mido.MidiTrack()
                        channels[ch].append(msg)
                for ch in channels:
                    mid_channel = mido.MidiFile()
                    mid_channel.tracks.append(channels[ch])
                    fp = io.BytesIO()
                    mid_channel.save(file=fp)
                    self.add_file("channel{0}.mid".format(ch), fp.getvalue(),
                                  self.filesystem['/'].directories["track"].directories["track{0}".format(i)],
                                  FILE_MODE)

    def getattr(self, path, fh=None):
        st = self.get_file(path)
        if not st:
            st = self.get_dir(path)
        if not st:
            raise FuseOSError(errno.ENOENT)
        return st.properties.__dict__

    def readdir(self, path, fh):
        st = self.get_dir(path)
        return ['.', '..'] + [x for x in st.files] + [x for x in st.directories]

    def read(self, path, size, offset, fh):
        file_obj = self.get_file(path)
        return file_obj.data[offset:(offset + size)]

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def get_file(self, path):
        if path[-1] == '/':
            return None
        else:
            path_array = path.split('/')
            file_name = path_array.pop()
            dir_name = '/'.join(path_array)
            location = self.get_dir(dir_name)
            if file_name in location.files:
                return location.files[file_name]
            return None

    def get_dir(self, path):
        path = path.rstrip('/')
        path_array = path.split('/')
        if len(path_array) <= 1:
            return self.filesystem['/']
        path_array.pop(0)
        location = self.filesystem['/']
        while path_array:
            dir_path = path_array.pop(0)
            if dir_path in location.directories:
                location = location.directories[dir_path]
            else:
                return None
        return location

    @staticmethod
    def add_dir(dir_name, parent_obj: Directory, mode):
        parent_obj.directories[dir_name] = Directory(files={}, directories={},
                                                     properties=Property(st_mode=mode, st_nlink=2,
                                                                         st_ctime=NOW, st_mtime=NOW,
                                                                         st_atime=NOW, st_size=0))
        parent_obj.properties.st_nlink += 1

    def add_file(self, file_name, data, dir_obj, mode):
        size = len(data)
        dir_obj.files[file_name] = File(data=data, properties=Property(st_mode=mode, st_nlink=1,
                                                                       st_size=size, st_ctime=NOW,
                                                                       st_mtime=NOW, st_atime=NOW))
        self.fd += 1
        dir_obj.properties.st_nlink += 1


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Filesystem MIDI Sequencer")
    parser.add_argument('midi_file')
    parser.add_argument('mount')

    args = parser.parse_args()
    fuse = FUSE(MIDISequencer(args.midi_file), mountpoint=args.mount, foreground=True, debug=True)
