#!/usr/bin/env python
# author: Lefteris Karapetsas
# email: lefteris@refu.co

import subprocess
import argparse
import time
import filecmp
import shutil
from os import listdir
from os.path import isfile, join, getmtime, basename

shouldNotfy = True
shouldCopyToDropbox = False
shouldCopyToSteam = False

def isclose(a, b, rel_tol=1e-09, abs_tol=0.0):
    return abs(a-b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)


def defaultSaveNameCB(f):
    return basename(f)


class GameEntry():
    def __init__(
            self,
            name,
            steamPath,
            dropboxPath,
            saveSuffix=None,
            saveNameCB=None
    ):
        """
        A Game Entry. It consists of:
            name:               A name for the game
            steamPath:          Path where steam stores the saves for this game
            dropboxPath:        Dropbox path where you need the saves backedup.
                                Will be created if it does not exist.
            saveSuffix:         Optional suffix for the save game files. If it
                                is not None then only files with the given
                                suffix in the directory will be considered.
            saveNameCB:         Optional callback to determine the name
                                of the save file to compare by checking the
                                filename or contents. If the function returns
                                \"__IGNORE__\" then that save file is ignored.
                                if the function returns the empty string
                                there has been an error
        """
        self.name = name
        self.dropboxPath = dropboxPath
        self.steamPath = steamPath
        self.saveSuffix = saveSuffix
        self.saveNameCB = saveNameCB
        if not saveNameCB:
            self.saveNameCB = defaultSaveNameCB


def POESaveName(f):
    """
    Pillars of Eternity change name depending on in-game location where the
    save happens but there is a hash number which always stays constant.
    Extract this and consider it as the save name.

    Ignore autosaves.
    """
    name = basename(f)
    res = name.rpartition(" ")
    if res[0] == "" and res[1] == "":
        return ""
    if res[2].startswith("autosave_"):
        return "__IGNORE__"
    return res[0]


gamesList = [
    GameEntry(
        "PillarsOfEternity",
        "/home/lefteris/.local/share/PillarsOfEternity/SavedGames",
        "/home/lefteris/Dropbox/saves/PillarsOfEternity",
        "savegame",
        POESaveName
    )
]


def getFileList(path, saveSuffix):
    filesList = [join(path, f) for f in listdir(path) if isfile(join(path, f))]
    if saveSuffix:
        return [x for x in filesList if x.endswith(saveSuffix)]
    else:
        return filesList


def findFileFromBasename(fileList, gentry, baseName):
    for f in fileList:
        if gentry.saveNameCB(f) == baseName:
            return f
    return None


def compareFileTimes(file1, file2):
    """
    Compare last file modification time for file1 and file2. Returns 0 if they
    have been modified around the same time, 1 if file1 is newer and -1 if
    file2 is newer
    """
    t1 = getmtime(file1)
    t2 = getmtime(file2)

    if isclose(t1, t2):
        return 0
    elif t1 > t2:
        return 1
    else:
        return -1


def syncSave(fromFile, toFile, gentry):
    # shutil.copy(fromFile, toFile)
    print("Would copy {} to {}".format(fromFile, toFile))
    notify(
        "Synced save for {}".format(gentry.name),
        "Synced save \"{}\" {} Dropbox".format(
            gentry.saveNameCB(fromFile),
            "from" if fromFile.startswith(gentry.dropboxPath) else "to"
        ),
        "normal"
    )


def notify(title, message, priority):
    if shouldNotify:
        subprocess.call(["notify-send", "-t", "0", priority, title, message])


def syncEntry(gentry):
    """
    Takes a game entry and checks if saved games should be synced from/to
    Dropbox.
    """
    steamFiles = getFileList(gentry.steamPath, gentry.saveSuffix)
    dboxFiles = getFileList(gentry.dropboxPath, gentry.saveSuffix)

    for f in steamFiles:
        baseName = gentry.saveNameCB(f)
        if baseName == "":
            notify(
                "Failed to extract name from save file {}".format(f),
                "",
                "normal"
            )
            continue
        elif baseName == "__IGNORE__":
            continue
        dboxFile = findFileFromBasename(dboxFiles, gentry, baseName)
        if dboxFile:
            if not filecmp.cmp(dboxFile, f):
                # There is a corresponding file in dropbox
                # and the files are not the same
                cmpres = compareFileTimes(f, dboxFile)
                if cmpres == 0:
                    # Files are different but time is the same for both.
                    # Can't really do anything
                    notify(
                        "Failed to sync save for {}".format(gentry.name),
                        "Save file {} exists in both steam and dropbox with "
                        "different contents but same modification timestamp",
                        "critical"
                    )
                elif cmpres == 1:
                    # Steam file is newer
                    syncSave(f, dboxFile, gentry)
                elif cmpres == -1:
                    # Dropbox file is newer
                    syncSave(dboxFile, f, gentry)
                else:
                    # should never happen
                    notify("Internal script error", "", "critical")
                    exit(1)
        else:
            # There is no corresponding file in Dropbox, so let's store this
            syncSave(f, gentry.dropboxPath, gentry)

    steamFiles = getFileList(gentry.steamPath, gentry.saveSuffix)
    dboxFiles = getFileList(gentry.dropboxPath, gentry.saveSuffix)
    # Copy any files in dropbox not saved in local steam saves
    for f in dboxFiles:
        baseName = gentry.saveNameCB(f)
        if baseName == "":
            notify(
                "Failed to extract name from save file {}".format(f),
                "",
                "normal"
            )
            continue
        elif baseName == "__IGNORE__":
            continue
        steamFile = findFileFromBasename(steamFiles, gentry, baseName)
        if not steamFile:
            syncSave(f, gentry.steamPath, gentry)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sync game save files')
    parser.add_argument(
        '--no-notify',
        dest='shouldNotify',
        action='store_false',
        help='Don\'t use system\'s notify to write script results'
    )
    parser.add_argument(
        '--copy-to-dropbox',
        dest='copyToDropbox',
        action='store_true',
        help="Instead of trying to determine sync from save names "
        "simply copy from Steam to Dropbox"
    )
    parser.add_argument(
        '--copy-to-steam',
        dest='copyToSteam',
        action='store_true',
        help="Instead of trying to determine sync from save names "
        "simply copy from Dropbox to Steam"
    )
    parser.set_defaults(shouldNotify=True)
    parser.set_defaults(copyToSteam=False)
    parser.set_defaults(copyToDropbox=False)
    args = parser.parse_args()
    if args.shouldNotify:
        print("Called with notify")
    else:
        print("Called without notify")
    shouldNotify = args.shouldNotify
    shouldCopyToDropbox = args.copyToDropbox
    shouldCopyToSteam = args.copyToSteam

    if shouldCopyToDropbox or shouldCopyToSteam:
        print("Not yet implemented")
        exit(1)

    for g in gamesList:
        syncEntry(g)
