import os

from contextlib import suppress
from threading import Lock, Timer

import pywikibot

from pywikibot.bot import BaseBot
from pywikibot.exceptions import NoPageError


class ErrorReportingBot(BaseBot):

    file_name = None
    page_pattern = None

    def __init__(self, **kwargs):
        self.available_options.update({
            'clearonly': False,
            'interval': 5 * 60,
        })
        super().__init__(**kwargs)
        self.timer = None
        self.file_lock = Lock()
        self.timer_lock = Lock()

    def run(self):
        self.open()
        self.save_file()
        if not self.opt['clearonly']:
            super().run()

    def open(self):
        with suppress(OSError):
            f = open(os.path.join('..', self.file_name), 'x')
            f.close()

    @property
    def log_page(self):
        log_page = pywikibot.Page(
            self.repo, self.page_pattern % self.repo.username())
        try:
            log_page.get()
        except NoPageError:
            log_page.text = ''
        return log_page

    def append(self, text):
        with (
            self.file_lock,
            open(os.path.join('..', self.file_name), 'a', encoding='utf-8') as f
        ):
            f.write(text)

    def save_file(self):
        with (
            self.file_lock,
            open(os.path.join('..', self.file_name), 'r+', encoding='utf-8') as f
        ):
            f.seek(0)  # jump to the beginning
            text = '\n'.join(f.read().splitlines())  # multi-platform
            if text:
                log_page = self.log_page
                log_page.text += text
                log_page.save(summary='update')
                f.seek(0)  # jump to the beginning
                f.truncate()  # and delete everything
        with self.timer_lock:
            self.timer = Timer(self.opt['interval'], self.save_file)
            self.timer.start()

    def teardown(self):
        with self.timer_lock:
            if self.timer:
                self.timer.cancel()
        super().teardown()
