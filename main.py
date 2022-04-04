import json
import os
from telebotapi import TelegramBot
from utils import wait_for, Condition, Filter
from threading import Thread
from random import choice
from datetime import datetime, timedelta
from time import sleep
from colors import COLOR_MAP, NAME_MAP


t = TelegramBot("5139141922:AAG0isSx8jGoS6s-giOS6SSUUKWA49rWpQs")
t.bootstrap()


class Contributor:
    def __init__(self, u: TelegramBot.User, r: str):
        self.user = u
        self.r_username = r
        self.assigned = None
        self.last_assignment = datetime.now()
        self.history = []

    def archive(self):
        if self.assigned is None:
            return
        self.history.append(self.assigned)
        self.assigned = None
        contributors.write()

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
                "pixel": px,
                "last_assignment": self.last_assignment.timestamp()
            },
            "history": [
                i.serialize() for i in self.history
            ]
        }

    def assign(self):
        if self.assigned:
            pixelmap.pixel_done(self.assigned)
            self.archive()
        try:
            pixelmap.get_pixel().assign(self)
            self.last_assignment = datetime.now()
            contributors.write()
            return True
        except AttributeError:
            return

    def cooldown(self):
        return self.last_assignment + timedelta(minutes=5) <= datetime.now()


class Contributors:
    def __init__(self, pre_data=None):
        self.data = []
        if pre_data:
            for i in pre_data:
                self.data.append(Contributor(TelegramBot.User(i["telegram"]), i["reddit"]["username"]))
                if px := pixelmap.get(*i["reddit"]["pixel"]):
                    px.assign(self.data[-1])
                    self.data[-1].last_assignment = datetime.fromtimestamp(i["reddit"]["last_assignment"])
                    for k in i["history"]:
                        self.data[-1].history.append(pixelmap.get(k["x"], k["y"]))

    def add_contributor(self, c: Contributor):
        self.data.append(c)
        self.write()

    def serialize(self):
        out = []
        for d in self.data:
            out.append(d.serialize())
        return out

    def write(self):
        json.dump(self.serialize(), open("contributors.json", "w+"), indent=4)

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
        return f"Pixel({self.x}, {self.y}, {NAME_MAP[self.color]})"

    def serialize(self):
        return {
            "x": self.x,
            "y": self.y,
            "color": self.color
        }


class PixelMap:
    def __init__(self, pre_data):
        self.data = []
        for i in pre_data:
            self.data.append(Pixel(i["x"], i["y"], i["color"]))

    def get_pixel(self):
        not_assigned = list([i for i in self.data if not i.done and not i.user])
        if len(not_assigned) == 0:
            return
        return choice(not_assigned)

    def get(self, x, y) -> Pixel:
        for j in self.data:
            if j.x == x and j.y == y:
                return j

    def pixel_done(self, p: Pixel):
        self.get(p.x, p.y).done = True

    def serialize(self):
        out = []
        for j in self.data:
            out.append(j.serialize())
        return out

    def write(self):
        json.dump(self.serialize(), open("pixelmap.json", "w+"))

    def get_done(self):
        for i in self.data:
            if i.done:
                yield i


if os.path.exists("pixelmap.json"):
    pixelmap = PixelMap(json.load(open("pixelmap.json")))
else:
    print("No pixelmap found.")
    exit()


if os.path.exists("contributors.json"):
    contributors = Contributors(json.load(open("contributors.json")))
else:
    contributors = Contributors()

while contributors.get(TelegramBot.User.by_id(None, 461073396)).assign():
    pass


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
        if tgt.assign():
            t.sendMessage(msg.from_, f"Pixel assegnato! `{tgt.assigned.represent()}`")
        else:
            t.sendMessage(msg.from_, f"Non ci sono pixel disponibili per ora!")


def assign_force(msg: TelegramBot.Update.Message):
    tgt = contributors.get(msg.from_)

    tgt.assign()

    t.sendMessage(msg.from_, f"Pixel assegnato! `{tgt.assigned.represent()}`")


def history(msg: TelegramBot.Update.Message):
    tgt = contributors.get(msg.from_)
    out = "I tuoi pixel:\n"
    for i in tgt.history:
        out += f"- {i.represent()}\n"
    t.sendMessage(msg.from_, out)


def reminder(c: Contributors, p: PixelMap):
    while True:
        for i in c.data:
            if i.assigned and i.cooldown():
                i.archive()
                t.sendMessage(i.user,
                              "Hei ricordati di me, sono passati 5 minuti, puoi chiedermi un nuovo pixel se vuoi.")
                contributors.write()

        sleep(5)


tr = Thread(target=reminder, args=(contributors, pixelmap))
tr.start()

try:
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
        ),
        # list previously assignments
        Condition(
            Filter(lambda l: contributors.is_contributor(l.from_)),
            Filter(lambda l: l.text.split(" ")[0] == "/history"),
            callback=history
        )

    )
except Exception as e:
    contributors.write()
    raise e

