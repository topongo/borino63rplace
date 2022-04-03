from typing import Callable
from inspect import getsource
from telebotapi import TelegramBot
from datetime import datetime, timedelta
from time import sleep


class Filter:
    def __init__(self, comparer: Callable):
        self.comparer = comparer

    def call(self, msg):
        try:
            return self.comparer(msg)
        except AttributeError:
            print("Exception caught")
            return False

    def __str__(self):
        return f"Filter(\"{getsource(self.comparer).strip()}\""

    def __repr__(self):
        return str(self)


class Condition:
    def __init__(self, *filters: Filter, callback=lambda l: None, stop_return=None):
        self.callback = callback
        self.stop_return = stop_return
        self.filters = list(filters)

    def add_filter(self, *f):
        for i in f:
            self.filters.append(i)

    def meet(self, msg):
        return all(map(lambda l: l.call(msg), self.filters))

    def __str__(self):
        return f"Condition(\n    filters=[\n        " + ",\n        ".join(map(lambda l: str(l), self.filters))\
               + f"\n    ],\n    callback=\"{self.callback}\"," \
                 f"\n    stop_return={self.stop_return}\n)"

    def __repr__(self):
        return str(self)


def wait_for(t: TelegramBot,
             *conditions: Condition,
             timeout=300):

    t.daemon.delay = 0.5

    timeout_end = datetime.now() + timedelta(seconds=timeout)

    while True:
        for u in t.get_updates():
            for c in conditions:
                if c.meet(u.content):
                    c.callback(u.content)
                    if c.stop_return is not None:
                        if isinstance(c.stop_return, Callable):
                            return c.stop_return(u.content)
                        else:
                            return c.stop_return
        if timeout_end < datetime.now():
            return False
        sleep(0.1)
