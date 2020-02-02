import enum

import datetime
from aiokts.store import models


class FloatField(models.Field):
    def __init__(self, default=None, private=False):
        super().__init__(default, private)

    def transform_in(self, value):
        return float(value)


class User(models.Model):
    id = models.StringField()
    ok_user_id = models.IntField()
    session_key = models.StringField(private=True)
    session_secret = models.StringField(private=True)
    first_name = models.StringField()
    last_name = models.StringField()
    country = models.StringField(private=True)
    city = models.StringField(private=True)
    created_at = models.UnixTimestampField(private=True)
    last_active_at = models.UnixTimestampField(private=True)


class Game(models.Model):
    @enum.unique
    class Type(enum.IntEnum):
        mouse = 0
        gun = 1
        mobile = 2

    id = models.StringField()
    user_id = models.StringField()
    type = models.IntEnumField(Type, json_name=True)
    seed = models.IntField()
    created_at = models.UnixTimestampField()
    started_at = models.UnixTimestampField()
    finished_at = models.UnixTimestampField()
    score = models.IntField()
    score_front = models.IntField()
    score_back = models.IntField()
    score_ok = models.IntField()
    shoot_count = models.IntField()
    user_promo_id = models.IntField()
    week = models.IntField()  # FIXME

    def is_finished(self, game_duration):
        if int(self.started_at.timestamp()) > 0:
            delta = (datetime.datetime.now() - self.started_at).total_seconds()
            time_exceeded = delta >= (game_duration + 10)
        else:
            time_exceeded = False
        return int(self.finished_at.timestamp()) > 0 or time_exceeded


class Promo(models.Model):
    id = models.IntField()
    code = models.StringField()


class PromoUser(models.Model):
    id = models.IntField()
    promo_id = models.IntField()
    user_id = models.StringField()
    is_active = models.BooleanField()
    paid = models.BooleanField(private=True)


class TopScore(models.Model):
    id = models.IntField(private=True)
    user_id = models.StringField()
    user = models.DictField()
    score = models.IntField()
    score_ok = models.IntField()
    week = models.IntField(private=True)
    paid = models.BooleanField(private=True)
    banned = models.BooleanField(private=True)
    date = models.IntField(private=True)

    def __repr__(self):
        return f"TopScore<uid={self.user_id} week={self.week} " \
               f"score_ok={self.score_ok} date={self.date}>"


class Token(models.Model):
    token = models.StringField()
    user_id = models.StringField()
    ok_user_id = models.IntField()
    expires = models.IntField()
