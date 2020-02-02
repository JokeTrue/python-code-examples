import time
import uuid

import datetime

import math
import weakref

import numpy
from numpy.random import RandomState

from domestosgame.store.models.core import Game
from settings import settings

MS = 1000  # milliseconds in seconds


class Microbe(object):
    def __init__(self, factory, epoch, info, random_state):
        self._factory = weakref.ref(factory)
        self.id = uuid.uuid4().hex
        self.hp = 1

        self.epoch = epoch
        self.type = int(info['type'])
        self.width = float(info['width'])
        self.height = float(info['height'])

        self.cell_x = -1
        self.cell_y = -1
        self.x = 0.0
        self.y = 0.0
        self.random_state = random_state

        self.last_update = 0

        self._killed = False

    @property
    def factory(self):
        return self._factory()

    def is_hit(self, x, y, radius=None):
        border_left = self.x - self.width / 2
        border_right = self.x + self.width / 2

        border_bottom = self.y - self.height / 2
        border_top = self.y + self.height / 2

        if radius is not None:
            hit_left = x - radius
            hit_right = x + radius
            hit_bottom = y - radius
            hit_top = y + radius

            if hit_left > border_right:
                return False

            if hit_right < border_left:
                return False

            if hit_bottom > border_top:
                return False

            if hit_top < border_bottom:
                return False

            return True
        else:
            return border_left < float(x) < border_right \
                   and border_bottom < float(y) < border_top

    def damage(self):
        self.hp = 0
        return self.hp

    def kill(self):
        self._killed = True

    def _cell2coords(self, cell_x, cell_y):
        f = self.factory
        x = f.x_min + cell_x * f.cell_width + f.cell_width / 2
        y = f.y_min + cell_y * f.cell_height + f.cell_height / 2
        return x, y

    def set_position(self, microbes):
        f = self.factory
        cell_x = self.random_state.randint(0, f.cells_x)
        cell_y = self.random_state.randint(0, f.cells_y)
        x, y = self._cell2coords(cell_x, cell_y)

        coords = set(map(lambda m: (m.cell_x, m.cell_y), microbes))

        i = 0
        while (
            (cell_x == 0 and cell_y == f.cells_y - 1)
            or ((cell_x, cell_y) in coords)
        ):
            cell_x = self.random_state.randint(0, f.cells_x)
            cell_y = self.random_state.randint(0, f.cells_y)
            x, y = self._cell2coords(cell_x, cell_y)

            if i > 10:
                break

            i += 1

        self.cell_x = cell_x
        self.cell_y = cell_y

        self.x = round(x, 6)
        self.y = round(y, 6)

    @property
    def is_alive(self):
        return self.hp > 0 and not self._killed

    def to_dict(self):
        return {
            'epoch': self.epoch,
            'id': self.id,
            'type': self.type,
            'x': self.x,
            'y': self.y,
            'hp': self.hp,
        }

    def __str__(self):
        return str(self.to_dict())


class MicrobeFactory:
    def __init__(self,
                 user_id,
                 game_type,
                 store,
                 microbe_types,
                 n_in_epoch=6,
                 n_in_epoch_promo=10,
                 epoch_period=5000,
                 second_epoch_period=3000,

                 n_in_epoch_mobile=4,
                 n_in_epoch_promo_mobile=8,
                 epoch_period_mobile=1000,
                 second_epoch_period_mobile=1000,
                 ):
        self._user_id = user_id
        self._game_type = game_type
        self._store = store

        assert self._game_type is not None

        self._seed = int(time.time())
        self._rnd = RandomState(self._seed)
        self._microbes = []

        self._n_in_epoch = n_in_epoch
        self._n_in_epoch_promo = n_in_epoch_promo
        self._epoch_period = epoch_period
        self._second_epoch_period = second_epoch_period

        self._n_in_epoch_mobile = n_in_epoch_mobile
        self._n_in_epoch_promo_mobile = n_in_epoch_promo_mobile
        self._epoch_period_mobile = epoch_period_mobile
        self._second_epoch_period_mobile = second_epoch_period_mobile

        self.microbe_types = microbe_types

        self._epoch = 0
        self._last_epoch_time = None

        assert self.microbe_types is not None
        assert len(self.microbe_types) > 0
        for m in self.microbe_types:
            assert m['type'] > 0
            assert m['width'] > 0
            assert m['height'] > 0

        top_bar_size = self.game_cfg['top_bar_size']
        self.cell_width = self.game_cfg['cell_width']
        self.cell_height = self.game_cfg['cell_height']

        self.x_max = 1
        self.x_min = -1

        self.y_max = 1 - top_bar_size
        self.y_min = -1 + self.cell_height / 2

        self.cells_x = math.floor((self.x_max - self.x_min) / self.cell_width)
        self.cells_y = math.floor((self.y_max - self.y_min) / self.cell_height)

    @property
    def n_in_epoch(self):
        return self._n_in_epoch_mobile if \
            self.is_mobile() else self._n_in_epoch

    @property
    def n_in_epoch_promo(self):
        return self._n_in_epoch_promo_mobile if \
            self.is_mobile() else self._n_in_epoch_promo

    @property
    def epoch_period(self):
        return self._epoch_period_mobile if \
            self.is_mobile() else self._epoch_period

    @property
    def second_epoch_period(self):
        return self._second_epoch_period_mobile if \
            self.is_mobile() else self._second_epoch_period

    @property
    def store(self):
        return self._store

    @property
    def game_cfg(self):
        return settings.config['game']

    @property
    def user_id(self):
        return self._user_id

    @property
    def microbes(self):
        return self._microbes

    @property
    def epoch(self):
        return self._epoch

    def dump_microbes(self, microbes=None):
        if microbes is None:
            microbes = self.microbes
        return [m.to_dict() for m in microbes]

    def gen_microbes(self, has_promo):
        self._epoch += 1
        self._last_epoch_time = datetime.datetime.now()

        n = self.n_in_epoch
        if has_promo:
            n = self.n_in_epoch_promo

        new_microbes = []
        for _ in range(0, n):
            microbe_info_i = self._rnd.randint(0, len(self.microbe_types))
            m = Microbe(self,
                        self._epoch,
                        self.microbe_types[microbe_info_i],
                        self._rnd)
            m.set_position(self.microbes)
            self.microbes.append(m)
            new_microbes.append(m)
        return new_microbes

    def get_alive(self):
        return list(filter(lambda item: item.is_alive, self.microbes))

    def shoot(self, x, y, has_promo, radius=None):
        killed = []

        closest = list(sorted(
            self.get_alive(),
            key=lambda item:
            numpy.math.hypot(x - item.x, y - item.y)
        ))
        if has_promo:
            microbes = closest[:4]
        else:
            microbes = closest[:1]

        if len(microbes) > 0 and microbes[0].is_hit(x, y, radius):
            for m in microbes:
                if m.damage() <= 0:
                    killed.append(m.id)

        self._microbes = self.get_alive()
        score = len(killed)  # simple for just now
        return score, killed

    def check_world(self, game_started_at, current_time, has_promo):
        if self._last_epoch_time is None:
            self._last_epoch_time = game_started_at

        delta = (current_time - self._last_epoch_time).total_seconds() * MS

        epoch_to_delete = self._epoch - 1
        if self.is_mobile():
            epoch_to_delete = self._epoch

        if self._epoch >= 2 or self.is_mobile():
            # remove & generate
            if delta >= self.epoch_period:
                # removing epoch
                removed_microbes = []
                for m in self.microbes:

                    if m.epoch == epoch_to_delete:  # remove previous epoch
                        m.kill()
                        removed_microbes.append(m.id)

                # creating new epoch
                self._microbes = self.get_alive()
                new_microbes = self.gen_microbes(has_promo)
                return self.dump_microbes(new_microbes), removed_microbes
        else:
            # just add new epoch
            if delta >= self.second_epoch_period:
                # creating new epoch
                self.gen_microbes(has_promo)
                return self.dump_microbes(), []
        return None

    def is_mobile(self):
        return self._game_type == Game.Type.mobile
