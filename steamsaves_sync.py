#!/usr/bin/env python
# author: Lefteris Karapetsas
# email: lefteris@refu.co
#
# USE AT YOUR OWN RISK. First make a backup of your saves.
# This script is not guaranteed to work correctly at all times, especially
# for games other than those that are tested and have saveName and saveTime
# callbacks. Currently only PillarsOfEternity has been so tested.

import subprocess
import argparse
import time
import filecmp
import shutil
from os import listdir
from os.path import isfile, join, getmtime, basename
import zipfile
import xml.etree.ElementTree as ET
import datetime


shouldNotfy = True
shouldCopyToDropbox = False
shouldCopyToSteam = False


def isclose(a, b, rel_tol=1e-09, abs_tol=0.0):
    return abs(a-b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)


def defaultSaveNameCB(f):
    return basename(f)


def defaultGetSaveTime(f):
    return getmtime(f)


class GameEntry():
    def __init__(
            self,
            name,
            steamPath,
            dropboxPath,
            saveSuffix=None,
            saveNameCB=None,
            saveTimeCB=None
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
            saveTimeCB:         Optional callback to determine the in-game
                                time the save was performed. If not given
                                then the last file modification timestamp is
                                taken which can't really be very trustworthy.
        """
        self.name = name
        self.dropboxPath = dropboxPath
        self.steamPath = steamPath
        self.saveSuffix = saveSuffix
        self.saveNameCB = saveNameCB
        if not saveNameCB:
            self.saveNameCB = defaultSaveNameCB
        self.getSaveTime = saveTimeCB
        if not saveTimeCB:
            self.getSaveTime = defaultGetSaveTime


def POESaveName(f):
    """
    Pillars of Eternity saves are actually zip archives. We are interested in
    the saveinfo.xml file inside the archive since that contains the save game
    name we use in-game.

    Ignore autosaves.
    """
    name = basename(f)
    res = name.rpartition(" ")
    if res[0] == "" and res[1] == "":
        # malformed name
        return ""
    if res[2].startswith("autosave_"):
        # ignore autosaves
        return "__IGNORE__"

    # If we get here it's a user save. Get the user save name
    archive = zipfile.ZipFile(f, 'r')
    xmldata = archive.read('saveinfo.xml')
    root = ET.fromstring(xmldata)
    ret_name = ""
    for p in root[0].findall('Simple'):
        if p.get('name') == 'UserSaveName':
            ret_name = p.get('value')
            break
    return ret_name


def POESaveTime(f):
    """
    Pillars of Eternity saves are actually zip archives. We are interested in
    the actual save was performed by the player.
    the saveinfo.xml file inside the archive since that contains the time

    Returns 0 if there is an error or the unix timestamp if it's determined
    """
    archive = zipfile.ZipFile(f, 'r')
    xmldata = archive.read('saveinfo.xml')
    root = ET.fromstring(xmldata)
    ret_ts = 0
    for p in root[0].findall('Simple'):
        if p.get('name') == 'RealTimestamp':
            sdate = p.get('value')
            ret_ts = time.mktime(datetime.datetime.strptime(
                sdate, "%m/%d/%Y %H:%M:%S").timetuple()
            )
            break
    return ret_ts

gamesList = [
    GameEntry(
        "PillarsOfEternity",
        "/home/lefteris/.local/share/PillarsOfEternity/SavedGames",
        "/home/lefteris/Dropbox/saves/PillarsOfEternity",
        "savegame",
        POESaveName,
        POESaveTime
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


def compareFileTimes(file1, file2, gentry):
    """
    Compare last file modification time for file1 and file2. Returns 0 if they
    have been modified around the same time, 1 if file1 is newer and -1 if
    file2 is newer
    """
    t1 = gentry.getSaveTime(file1)
    t2 = gentry.getSaveTime(file2)

    if t1 == 0 or t2 == 0:
        print("Failed to get time from a Save Game File")
        exit(1)

    if isclose(t1, t2):
        return 0
    elif t1 > t2:
        return 1
    else:
        return -1


def syncSave(fromFile, toFile, gentry):
    shutil.copy(fromFile, toFile)
    notify(
        "Synced save for {}".format(gentry.name),
        "Synced save \"{}\" {} Dropbox".format(
            gentry.saveNameCB(fromFile),
            "from" if fromFile.startswith(gentry.dropboxPath) else "to"
        ),
        "normal"
    )


def savesAreSame(s1, s2):
    return filecmp.cmp(s1, s2)


def notify(title, message, priority):
    if shouldNotify:
        subprocess.call([
            "notify-send",
            "-t", "4",
            "-u", priority,
            title,
            message
        ])
    print("sync_saves [{}]:\t{}\n\t\t\t{}".format(priority, title, message))


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
            if not savesAreSame(dboxFile, f):
                # There is a corresponding file in dropbox
                # and the files are not the same
                cmpres = compareFileTimes(f, dboxFile, gentry)
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

    shouldNotify = args.shouldNotify
    shouldCopyToDropbox = args.copyToDropbox
    shouldCopyToSteam = args.copyToSteam

    if shouldCopyToDropbox or shouldCopyToSteam:
        print("Not yet implemented")
        exit(1)

    for g in gamesList:
        syncEntry(g)
