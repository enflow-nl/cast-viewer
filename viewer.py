#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from os import path, getenv, utime
from random import shuffle
from time import sleep
from json import load as json_load
from lib.system import is_under_voltage
from lib.utils import file_get_contents
from lib.utils import is_debugging
from lib.system import get_status
from lib.system import device_uuid
from lib.heartbeater import send_heartbeat
import logging
import sh
import sys
import os
import urllib
import socket
import json
import rollbar
import threading
import requests
import subprocess

from lib.downloader import Downloader
from lib.scheduler import Scheduler
from lib.pusher import Pusher
from lib.browser import Browser

__author__ = "Enflow (original by WireLoad Inc)"
__copyright__ = "Copyright 2012-2016, WireLoad Inc"
__license__ = "Dual License: GPLv2 and Commercial License"

EMPTY_BROADCAST_DELAY = 10  # secs

browser = None
scheduler = None
schedulerThread = None
downloader = None
server = None

def start_playing_video(uri, duration=None, loop=None):
    global browser

    player_args = []

    if duration and duration != 'N/A':
        player_args = ['timeout', duration]

    return sh.omxplayer(uri, timeout=duration, loop=True, o='hdmi', _bg=True, b=True, _ok_code=[0, 124])

status_overlay = None

def broadcast_loop(scheduler):
    global browser, status_overlay, loading_video

    if loading_video is not None:
        loading_video.kill()
        loading_video = None

    still_has_statusoverlay = False

    if scheduler.state == scheduler.STATE_NO_CONNECTION:
        if scheduler.slides is not empty:
            browser.template('no_connection')
            sleep(EMPTY_BROADCAST_DELAY)
            return
        else:
            still_has_statusoverlay = True

            if not status_overlay:
                status_overlay = sh.pngview("./public/img/no-internet-connection.png", n=True, b="0xffffffff", _bg=True)

    if status_overlay and not still_has_statusoverlay:
        status_overlay.kill()

    if scheduler.state == scheduler.STATE_REQUIRES_SETUP:
        browser.template('setup', {'player_identifier': device_uuid()[:7]})
        sleep(EMPTY_BROADCAST_DELAY)
        return

    if scheduler.state == scheduler.STATE_INTERNAL_SERVER_ERROR:
        browser.template('internal_server_error')
        sleep(EMPTY_BROADCAST_DELAY)
        return

    slide = scheduler.next_slide()

    if slide is None:
        browser.template('no_slides')
        sleep(EMPTY_BROADCAST_DELAY)
        return

    type, load = slide['type'], get_slide_url(slide)

    logging.info('Showing slide %s (%s)', type, load)

    preloadable_slide = scheduler.slide_to_preload()

    if 'web' in type:
        browser.url(load)

        duration = int(slide['duration'])

        sleep(1)

        browser.preload(preloadable_slide, get_slide_url(preloadable_slide))

        sleep(duration - 1)
    elif 'video' or 'streaming' in type:
        browser.preload(preloadable_slide, get_slide_url(preloadable_slide))

        run = start_playing_video(load, slide['duration'])

        while run.process.alive:
            sleep(1)
        if run.exit_code == 124:
            logging.info('omxplayer timed out')
    else:
        logging.error('Unknown type %s', type)


def get_slide_url(slide):
    if 'video' in slide['type']:
        return downloader.get_path_for_slide(slide)

    return slide['url']


def run_scheduler():
    global scheduler, browser

    logging.debug('Running scheduler thread')

    if scheduler.fetch():
        browser.template('loading')

        def callback(current, total):
            print(current, total)
            browser.template('loading', {'current': current, 'total': total})

        downloader.download(scheduler.slides, callback)

    logging.debug('Scheduler state: %s', scheduler.state)


def wait_for_scheduler():
    global schedulerThread, scheduler
    logging.debug("Waiting on scheduler to finish")

    schedulerThread.join()
    schedulerThread = None

loading_video = None

def main():
    global scheduler, schedulerThread, downloader, browser, loading_video

    if is_debugging():
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
    else:
        rollbar.init('eb9b246b01a64b65885a8d2113f39bde', 'production')

    loading_video = start_playing_video('./public/videos/loading.mp4', loop=True)

    downloader = Downloader()
    scheduler = Scheduler()
    browser = Browser()
    schedulerThread = None
    Pusher()

    browser.start()

    t = threading.Thread(target=send_heartbeat)
    t.daemon = True
    t.start()

    while True:
        if not scheduler.slides or len(scheduler.slides) - 1 == scheduler.index or scheduler.state != scheduler.STATE_OK:
            schedulerThread = threading.Thread(target=run_scheduler)
            schedulerThread.start()
            if not scheduler.slides and schedulerThread.isAlive():
                wait_for_scheduler()

        broadcast_loop(scheduler)

        if scheduler.index is 0 and schedulerThread and schedulerThread.isAlive():
            wait_for_scheduler()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit) as e:
        pass
    except:
        logging.exception("Beamy crashed.")

        if not is_debugging():
            rollbar.report_exc_info()

        raise
