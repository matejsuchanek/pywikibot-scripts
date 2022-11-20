import pywikibot

from pywikibot.bot import BaseBot


class DeferredCallbacksBot(BaseBot):

    '''
    Bot deferring callbacks like purging pages
    '''

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.callbacks = []

    def addCallback(self, func, *data, **kwargs):
        callback = lambda *_, **__: func(*data, **kwargs)
        self.callbacks.append(callback)

    def queueLen(self):
        return len(self.callbacks)

    def hasCallbacks(self):
        return self.queueLen() > 0

    def doWithCallback(self, func, *data, **kwargs):
        if self.hasCallbacks():
            kwargs['callback'] = self.callbacks.pop(0)
        return func(*data, **kwargs)

    def exit(self):
        pywikibot.info(f'Executing remaining deferred callbacks: {self.queueLen()} left')
        try:
            while self.hasCallbacks():
                callback = self.callbacks.pop(0)
                callback()
        finally:
            super().exit()
