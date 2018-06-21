# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import pywikibot
import threading

from pywikibot.bot import BaseBot


class ErrorReportingBot(BaseBot):

    file_name = None
    page_pattern = None

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'clearonly': False,
            'interval': 5 * 60,
        })
        super(ErrorReportingBot, self).__init__(**kwargs)
        self.timer = None
        self.file_lock = threading.Lock()
        self.timer_lock = threading.Lock()

    def run(self):
        self.open()
        self.load_page()
        self.save_file()
        if not self.getOption('clearonly'):
            super(ErrorReportingBot, self).run()

    def open(self):
        try:
            open(os.path.join('..', self.file_name), 'x', encoding='utf-8').close()
        except OSError:
            pass

    def load_page(self):
        self.log_page = pywikibot.Page(
            self.repo, self.page_pattern % self.repo.username())
        try:
            self.log_page.get()
        except pywikibot.NoPage:
            self.log_page.text = ''

    def append(self, text):
        with self.file_lock:
            with open(os.path.join('..', self.file_name), 'a', encoding='utf-8') as f:
                f.write(text)

    def save_file(self):
        with self.file_lock:
            with open(os.path.join('..', self.file_name),
                      'r+', encoding='utf-8') as f:
                f.seek(0)  # jump to the beginning
                text = '\n'.join(f.read().splitlines())  # multi-platform
                if text:
                    self.log_page.text += text
                    self.log_page.save(summary='update')
                    f.seek(0)  # jump to the beginning
                    f.truncate()  # and delete everything
        with self.timer_lock:
            self.timer = threading.Timer(
                self.getOption('interval'), self.save_file)
            self.timer.start()

    def teardown(self):
        with self.timer_lock:
            if self.timer:
                self.timer.cancel()
        super(ErrorReportingBot, self).teardown()
