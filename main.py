import json
import os
from telebotapi import TelegramBot
from utils import wait_for, Condition, Filter
from threading import Thread
from random import choice
from datetime import datetime, timedelta
from time import sleep


t = TelegramBot("5139141922:AAG0isSx8jGoS6s-giOS6SSUUKWA49rWpQs")
t.bootstrap()


class Contributor:
    def __init__(self, u: TelegramBot.User, r: str):
        self.user = u
        self.r_username = r
        self.assigned = None
        self.last_assignment = datetime.now()

    def serialize(self):
        try:
            px = [
                self.assigned.x,
                self.assigned.y
            ]
        except AttributeError:
            px = [-1, -1]
        return {
            "telegram": self.user.raw,
            "reddit": {
                "username": self.r_username,
                "pixel": px
            }
        }

    def assign(self, pm):
        assert isinstance(pm, PixelMap)
        if self.assigned:
            pm.pixel_done(self.assigned)
        pm.get_pixel().assign(self)
        self.last_assignment = datetime.now()

    def cooldown(self):
        return self.last_assignment + timedelta(minutes=5) <= datetime.now()


class Contributors:
    def __init__(self, pre_data=None):
        self.data = []
        if pre_data:
            for i in pre_data:
                self.data.append(Contributor(TelegramBot.User(i["telegram"]), i["reddit"]["username"]))
                if px := pixelmap.get(*i["reddit"]["px"]):
                    px.assign(self.data[-1])
                    self.data[-1].last_assignment = datetime.fromtimestamp(i["reddit"]["last_assignment"])

    def add_contributor(self, c: Contributor):
        self.data.append(c)
        self.write()

    def serialize(self):
        out = []
        for d in self.data:
            out.append(d.serialize())
        return out

    def write(self):
        json.dump(self.serialize(), open("contributors.json", "w+"))

    def is_contributor(self, u: TelegramBot.User):
        for i in self.data:
            if u.id == i.user.id:
                return True
        return False

    def get(self, u: TelegramBot.User):
        for i in self.data:
            if u.id == i.user.id:
                return i
        return None


class Pixel:
    COLORS = [
        "burgundy",
        "dark red",
        "red",
        "orange",
        "yellow",
        "pale yellow",
        "dark green",
        "green",
        "light green",
        "dark teal",
        "teal",
        "light teal",
        "dark blue",
        "blue",
        "light blue",
        "indigo",
        "periwinkle",
        "lavender",
        "dark purple",
        "purple",
        "pale purple",
        "magenta",
        "pink",
        "light pink",
        "dark brown",
        "brown",
        "beige",
        "black",
        "dark gray",
        "gray",
        "light gray",
        "white"
    ]

    def __init__(self, x, y, color, done=None):
        self.x = x
        self.y = y
        self.rx = -1
        self.ry = -1
        self.user = None
        self.color = color
        self.done = bool(done)

    def assign(self, u: Contributor):
        if self.user is None:
            self.user = u
            self.user.assigned = self

    def represent(self):
        return f"Pixel({self.x}, {self.y}, {self.COLORS[self.color]})"


class PixelMap:
    def __init__(self, pre_data=None):
        self.data = []
        if pre_data:
            for i in pre_data:
                self.data.append([])
                for j in i:
                    self.data[-1].append(Pixel(j["x"], j["y"], j["color"]))

    def get_pixel(self):
        r = choice(choice(self.data))
        while r.user or r.done:
            r = choice(choice(self.data))
        return r

    def get(self, x, y) -> Pixel:
        for i in self.data:
            for j in i:
                if j.x == x and j.y == y:
                    return j

    def pixel_done(self, p: Pixel):
        self.get(p.x, p.y).done = True


if os.path.exists("pixelmap.json"):
    pixelmap = PixelMap(json.load(open("pixelmap.json")))
else:
    pixelmap = PixelMap()


if os.path.exists("contributors.json"):
    contributors = Contributors(json.load(open("contributors.json")))
else:
    contributors = Contributors()


def new_contributor(msg: TelegramBot.Update.Message):
    if "u/" not in msg.text:
        t.sendMessage(msg.from_, "Se vuoi partecipare al progetto inviami il tuo username di reddit. "
                                 "Ex: `u/iltuousername`")
    else:
        user = msg.text.replace("u/", "").strip()
        t.sendMessage(msg.from_, f"Il tuo username è **u/{user}?** "
                                 f"Se non lo è invia questo comando: `/changereddit u/iltuousername`")
        contributors.add_contributor(Contributor(msg.from_, user))


def change_r_name(msg: TelegramBot.Update.Message):
    txt = msg.text.split(" ")[1].strip()
    if "u/" not in txt:
        t.sendMessage(msg.from_, "Se vuoi partecipare al progetto inviami il tuo username di reddit. "
                                 "Ex: `u/iltuousername`")
    else:
        user = txt.replace("u/", "").strip()
        contributors.get(msg.from_).r_username = user
        contributors.write()
        t.sendMessage(msg.from_, f"Username cambiato in u/{user}")


def assign(msg: TelegramBot.Update.Message):
    tgt = contributors.get(msg.from_)
    if tgt.assigned and not tgt.cooldown():
        t.sendMessage(msg.from_, f"Hai già un pixel assegnato: {tgt.assigned.represent()}\n"
                                 f"Usa /forceassign per fartene assegnare uno prima dello scadere dei 5 minuti.")
    else:
        tgt.assign(pixelmap)
        t.sendMessage(msg.from_, f"Pixel assegnato! `{tgt.assigned.represent()}`")


def assign_force(msg: TelegramBot.Update.Message):
    tgt = contributors.get(msg.from_)

    tgt.assign(pixelmap)
    t.sendMessage(msg.from_, f"Pixel assegnato! `{tgt.assigned.represent()}`")


def reminder(c: Contributors, p: PixelMap):
    for i in c.data:
        if i.assigned and i.cooldown():
            i.assigned = None
            t.sendMessage(i.user, "Hei ricordati di me, sono passati 5 minuti, puoi chiedermi un nuovo pixel se vuoi.")
    sleep(5)


tr = Thread(target=reminder, args=(contributors, pixelmap))
tr.start()

wait_for(
    t,
    # new subscriptions
    Condition(
        Filter(lambda l: not contributors.is_contributor(l.from_)),
        callback=new_contributor
    ),
    # change reddit name
    Condition(
        Filter(lambda l: contributors.is_contributor(l.from_)),
        Filter(lambda l: l.text.split(" ")[0] == "/changereddit" and len(l.text.split(" ")) > 1),
        callback=change_r_name
    ),
    # assign me one pixel
    Condition(
        Filter(lambda l: contributors.is_contributor(l.from_)),
        Filter(lambda l: l.text.split(" ")[0] == "/assign"),
        callback=assign
    ),
    # forcibly assign a new pixel
    Condition(
        Filter(lambda l: contributors.is_contributor(l.from_)),
        Filter(lambda l: l.text.split(" ")[0] == "/forceassign"),
        callback=assign_force
    )

)

