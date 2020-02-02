import enum
import hashlib
import re
import socket
import uuid

import datetime
import weakref

from logging import getLogger
from socketio import AsyncServer

from domestosgame.game.microbe import MicrobeFactory
from domestosgame.store.models.core import Game
from settings import settings

DOMAIN_RE = re.compile(r'special(\d+)\..*')


class GameRooms:
    def __init__(self, app, namespace):
        self._app = weakref.ref(app)
        self._sio_namespace = namespace
        self._rooms = {}
        self._sid_to_room = {}

    @property
    def app(self):
        return self._app()

    @property
    def store(self):
        return self.app.store

    @property
    def server(self):
        return self._sio_namespace

    def has_token(self, token):
        return token in self._rooms

    def get_room(self, token):
        return self._rooms.get(token)

    def get_room_by_sid(self, sid):
        return self._sid_to_room.get(sid)

    async def create_room(self, user_id, ok_user_id, screen_sid, gun_sid=None):
        r = Room(self, user_id, ok_user_id, screen_sid, gun_sid)
        await r.gen_token()

        self._rooms[r.token] = r
        assert screen_sid not in self._sid_to_room, 'Conflict on screen_sid'
        self._sid_to_room[screen_sid] = r
        return r

    def add_to_room(self, room, sid):
        self._sid_to_room[sid] = room

    def delete_room(self, token):
        # print('Calling delete_room', len(self._rooms))
        r = self.get_room(token)
        if r is None:
            return

        if r.screen_sid:
            del self._sid_to_room[r.screen_sid]

        if r.gun_sid:
            del self._sid_to_room[r.gun_sid]

        del self._rooms[token]

    def delete_sid(self, sid):
        if sid is not None:
            del self._sid_to_room[sid]


class Room:
    class DeviceType(enum.Enum):
        screen = 'screen'
        gun = 'gun'

    def __init__(self, game_rooms, user_id, ok_user_id, screen_sid, gun_sid=None):
        self._game_rooms = weakref.ref(game_rooms)

        self._user_id = user_id
        self._ok_user_id = ok_user_id
        self.screen_sid = screen_sid
        self.gun_sid = gun_sid

        self._microbe_factory = None
        self.token = None
        self.game_cfg = settings.config.get('game', {})

        self._game = None
        self._game_type = None

        self.logger = getLogger(f'room{self._ok_user_id}')

    @property
    def user_id(self):
        return self._user_id

    @property
    def game_id(self):
        return self._game.id if self._game is not None else None

    @property
    def game(self):
        return self._game

    @property
    def game_type(self):
        return self._game_type

    @property
    def server(self) -> AsyncServer:
        return self.rooms.server

    @property
    def rooms(self) -> GameRooms:
        return self._game_rooms()

    @property
    def store(self):
        if self.rooms is None:
            return None
        return self.rooms.store

    async def has_promo(self):
        return await self.store.user.has_promo(self.user_id)

    @property
    async def current_game(self):
        return await self.store.game.get(self.game_id)

    @property
    def cfg_game_duration(self):
        return self.game_cfg.get('duration', 60)

    async def _create_microbe_factory(self):
        factory_cfg = self.game_cfg.get('microbe_factory', {})
        return MicrobeFactory(
            store=self.store,
            user_id=self.user_id,
            game_type=self._game_type,
            n_in_epoch=factory_cfg.get('n_in_epoch', 6),
            n_in_epoch_promo=factory_cfg.get('n_in_epoch_promo', 10),
            epoch_period=factory_cfg.get('epoch_period', 3000),
            second_epoch_period=factory_cfg.get('second_epoch_period', 5000),
            n_in_epoch_mobile=factory_cfg.get('n_in_epoch_mobile', 4),
            n_in_epoch_promo_mobile=factory_cfg.get('n_in_epoch_promo_mobile', 8),
            epoch_period_mobile=factory_cfg.get('epoch_period_mobile', 2000),
            second_epoch_period_mobile=factory_cfg.get('second_epoch_period_mobile', 2000),

            microbe_types=factory_cfg.get('microbe_types')
        )

    async def gen_token(self):
        t = await self.store.token.save(user_id=self.user_id)
        self.token = t.token
        return self.token

    async def emit_event(self, sid, event_name, data=None):
        if data is not None and 'event' in data:
            d = data
        else:
            d = {'event': event_name}
            if data is not None:
                d.update(data)

        return await self.server.emit('message', d, room=sid)

    async def on_screen_connected(self, game_type: Game.Type):
        print('on screen connected')
        resp = {
            'has_promo': await self.has_promo()
        }

        self._game_type = game_type
        if game_type == Game.Type.gun:
            resp['token'] = self.token

            sticky_session = settings.config.get('sticky_session', False)
            if sticky_session:
                base_domain = settings.config['domain']
                hostname = socket.gethostname()

                m = DOMAIN_RE.match(hostname)
                if m is not None:
                    host_id = int(m.group(1))
                    resp['domain'] = f's{host_id}.{base_domain}'

        await self.emit_event(self.screen_sid, 'screen:connected', resp)

    async def on_gun_connected(self, gun_sid):
        self.gun_sid = gun_sid
        self.rooms.add_to_room(self, self.gun_sid)

        await self.emit_event(self.screen_sid, 'gun:connected', {
            'has_promo': await self.has_promo(),
            'game_duration': self.cfg_game_duration,
        })

    async def on_gun_disconnected(self):
        await self.emit_event(self.screen_sid, 'gun:disconnected')
        self.rooms.delete_sid(self.gun_sid)
        self.gun_sid = None

    async def disconnect_all(self):
        if self.screen_sid is not None:
            await self.server.disconnect(self.screen_sid)

        if self.gun_sid is not None:
            await self.server.disconnect(self.gun_sid)

        self.rooms.delete_room(self.token)

    async def on_message(self, data):
        event = data.get('event')
        if self.game_cfg.get('log_events', False):
            self.logger.info(f"{event}: {data}")

        f = {
            'gun:move': self._on_gun_move,
            'gun:calibrate': self._on_gun_calibrate,
            'screen:game_start': self._on_game_start,
            'screen:world_step': self._on_screen_world_step,
            'gun:shoot': self._on_gun_shoot,
            'screen:shoot': self._on_screen_shoot,
            'screen:game_stop': self._on_game_stop,
        }.get(event)

        if f is None:
            return
        return await f(data)

    async def _on_gun_move(self, data):
        await self.emit_event(self.screen_sid, None, data)

    async def _on_gun_calibrate(self, data):
        if self.gun_sid is not None:
            await self.emit_event(self.gun_sid, 'gun:calibrate', {
                'has_promo': await self.has_promo()
            })

    async def _on_game_start(self, data):
        self._microbe_factory = await self._create_microbe_factory()
        self._game = await self.store.game.create(self.user_id, self._game_type)
        has_promo = await self.has_promo()

        self._microbe_factory.gen_microbes(has_promo)
        resp = {
            'game_duration': self.cfg_game_duration,
            'has_promo': has_promo,
            'game_id': self._game.id,
            'type': self._game_type.name,
            'epoch': self._microbe_factory.epoch,
            'microbes': self._microbe_factory.dump_microbes()
        }

        self._game = await self.store.game.start(self._game.id)
        await self.emit_event(self.screen_sid, 'screen:game_started', resp)

        if self.gun_sid is not None:
            await self.emit_event(self.gun_sid, 'gun:game_started', {
                'has_promo': has_promo
            })

    async def _on_screen_world_step(self, data):
        started_at = self.game.started_at
        current_time = datetime.datetime.now()

        has_promo = await self.has_promo()

        res = self._microbe_factory.check_world(started_at,
                                                current_time,
                                                has_promo)
        if res is not None:
            new_microbes, removed_microbes = res
            await self.emit_event(self.screen_sid, 'screen:world_changed', {
                'epoch': self._microbe_factory.epoch,
                'new_microbes': new_microbes,
                'removed_microbes': removed_microbes,
            })

    async def _on_gun_shoot(self, data):
        await self.emit_event(self.screen_sid, None, data)

    async def _on_screen_shoot(self, data):
        if self._game is None:
            return
        if self._game.is_finished(self.cfg_game_duration):
            return

        x, y, radius = data.get('x'), data.get('y'), data.get('radius')
        if x is None or y is None:
            return

        self._game = await self.store.game.inc_shoot_count(self.game_id, 1)
        has_promo = await self.has_promo()

        score, killed_microbes = self._microbe_factory.shoot(x, y,
                                                             has_promo,
                                                             radius)
        if len(killed_microbes) > 0:
            self._game = await self.store.game.inc_score(self.game_id, score)
            await self.emit_event(self.screen_sid, 'screen:killed', {
                'killed': killed_microbes,
                'score': self._game.score,
            })

    async def _on_game_stop(self, data):
        score_front = data.get('score', 0)
        if self._game is None:
            return
        if not self._game.is_finished(self.cfg_game_duration):
            has_promo = await self.has_promo()
            self._game = await self.store.game.stop(self.game_id, score_front,
                                                    has_promo)

            res = {
                'score': self._game.score,
                'points': self._game.score_ok,
                'force': data.get('force', False)
            }

            await self.emit_event(self.screen_sid, 'screen:game_stopped', res)
            if self.gun_sid is not None:
                await self.emit_event(self.gun_sid, 'gun:game_stopped', res)
