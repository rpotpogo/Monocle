from sqlalchemy import Column
from sqlalchemy.types import Integer, BigInteger, Boolean, SmallInteger
from time import time
from . import db, utils, sanitized as conf

class WeatherCache:
    """Simple cache for storing actual weathers

    It's used in order not to make as many queries to the database.
    It schedules raids to be removed as soon as they expire.
    """
    def __init__(self):
        self.store = {}

    def __len__(self):
        return len(self.store)
        
    def __getitem__(self, index):
        return self.store[index]

    def add(self, weather):
        self.store[weather['s2_cell_id']] = weather

    def remove(self, cache_id):
        try:
            del self.store[cache_id]
        except KeyError:
            pass

    def __contains__(self, raw_weather):
        try:
            weather = self.store[raw_weather['s2_cell_id']]
            return (weather['condition'] == raw_weather['condition'] and
                weather['alert_severity'] == raw_weather['alert_severity'] and
                weather['warn'] == raw_weather['warn'] and
                weather['day'] == raw_weather['day'])
        except KeyError:
            return False

class Weather(db.Base):
    __tablename__ = 'weather'

    id = Column(Integer, primary_key=True)
    s2_cell_id = Column(db.UNSIGNED_HUGE_TYPE)
    condition = Column(SmallInteger)
    alert_severity = Column(SmallInteger)
    warn = Column(Boolean)
    day = Column(SmallInteger)
    updated = Column(Integer, default=time, onupdate=time)

    @classmethod
    def normalize_weather(self, raw, time_of_day):
        alert_severity = 0
        warn = False
        if raw.alerts:
            for a in raw.alerts:
                warn = warn or a.warn_weather
                if a.severity > alert_severity:
                    alert_severity = a.severity
        return {
            'type': 'weather',
            's2_cell_id': raw.s2_cell_id & 0xffffffffffffffff,
            'condition': raw.gameplay_weather.gameplay_condition,
            'alert_severity': alert_severity,
            'warn': warn,
            'day': time_of_day
        }

    @classmethod
    def add_weather(self, session, raw_weather):
        s2_cell_id = raw_weather['s2_cell_id']
    
        weather = session.query(Weather) \
            .filter(Weather.s2_cell_id == s2_cell_id) \
            .first()
        if not weather:
            weather = Weather(
                s2_cell_id=s2_cell_id,
                condition=raw_weather['condition'],
                alert_severity=raw_weather['alert_severity'],
                warn=raw_weather['warn'],
                day=raw_weather['day'],
                updated=int(time())
            )
            session.add(weather)
        else:
            weather.condition = raw_weather['condition']
            weather.alert_severity = raw_weather['alert_severity']
            weather.warn = raw_weather['warn']
            weather.day = raw_weather['day']
            weather.updated = int(time())
        WEATHER_CACHE.add(raw_weather)

WEATHER_CACHE = WeatherCache()
