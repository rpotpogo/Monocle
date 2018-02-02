import sys
import overpy
from shapely.geometry import Polygon, Point, LineString
import s2sphere
from .bounds import north, south, east, west
import json
from sqlalchemy import Column, or_, and_, delete, null
from sqlalchemy.types import Integer, BigInteger, Boolean, SmallInteger
from time import time
from . import db, utils, sanitized as conf 
from .shared import get_logger, LOOP

class Park(db.Base):
    __tablename__ = 'parks'

    id = Column(db.HUGE_TYPE)
    name = Column(db.String)
    coords = Column(db.String)
    updated = Column(Integer, default=time, onupdate=time)
    instanceid = Column(db.String)
    internalid = Column(Integer, primary_key=True, unique=True, autoincrement=True)

    @classmethod
    def remove_park(self, session, parkid=None):
        try:
            if not parkid:
                self.delete_gym_park(session)
                deleted = session.query(Park) \
                .filter(or_(Park.instanceid == db.instance_id, Park.instanceid == None)) \
                .delete()
            else:
                self.delete_gym_park(session, parkid)
                deleted = session.query(Park) \
                    .filter(or_(Park.instanceid == db.instance_id, Park.instanceid == None)) \
                    .filter(Park.id == parkid) \
                    .delete()
            session.commit()
            return deleted
        except Exception as e:
            raise e
            return 0


    @classmethod
    def delete_gym_park(self, session, parkid=None):
        try:
            updated = False
            if parkid:
                gyms = session.query(db.Fort) \
                      .filter(Fort.parkid == parkid) \
                      .with_for_update()
                if gyms:
                    for gym in gyms:
                        gym.park = null()
                        gym.parkid = null()
                    updated = True
            else:
                gyms = session.query(db.Fort) \
                      .join(Park, and_(Park.instanceid == db.instance_id, db.Fort.parkid == Park.internalid)) \
                      .all()
                if gyms:
                    for gym in gyms:
                        gym.park = null()
                        gym.parkid = null()
                    updated=True
            if updated:
                session.commit()
        except Exception as e:
            raise e


    @classmethod
    def add_park(self, session, raw_park):
#        try:
        pid = raw_park['id']
        pname = raw_park['name']
        pcoords = raw_park['coords']
        park = session.query(Park) \
            .filter(Park.id == pid) \
            .filter(Park.instanceid == db.instance_id) \
            .with_for_update() \
            .first()
        if not park:
            park = Park(
                id=pid,
                name=pname,
                coords=str(json.dumps(pcoords)),
                instanceid=db.instance_id
            )
            session.add(park)
        else:
            park.id = pid
            park.name = pname
            park.coords = str(json.dumps(pcoords))
            park.instanceid = db.instance_id
#        except Exception as e:
#            self.log.error("Error while adding new park ID {} : {}", raw_park['id'], e)

class Parks():

    def __init__(self):
        self.log = get_logger('parks')
        self.log.info('Parks initialized')
        self.PARKS_CACHE = ParksCache()

    def __enter__(self):
        self.PARKS_CACHE.preload()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def reset_parks(self, standalone=False):
#        try:
        self.log.info('Resetting parks table for this instance.')
        with db.session_scope() as session:
            deleted = Park.remove_park(session, None)
            session.commit()
            self.log.info("{} parks deleted from db", deleted)
        self.PARKS_CACHE.empty()
        self.fetch_all_parks(standalone)
#        except Exception as e:
#            self.log.error("Error while rsetting parks : {}", e)

    def fetch_all_parks(self, standalone=False):
        if not standalone and not conf.PARK_CHECK:
            self.log.info('Park check disabled in config')
            return
        try:
            self.log.info('Fetching all parks.')
            parks = self.get_all_parks()
            if len(parks) > 0:
                with db.session_scope() as session:
                    for p in parks:
                        if len(self.PARKS_CACHE) == 0 or p['id'] not in self.PARKS_CACHE:
                            Park.add_park(session,p)
                    session.commit()
                self.update_gyms()
                self.log.info('Forts parks updated.')
            else:
                self.log.info('No parks found for your area.')
        except Exception as e:
            self.log.error('Error while fetching parks : {}',e)

    def load(self):
        if len(self.PARKS_CACHE) == 0:
            self.fetch_all_parks()

    def get_all_parks(self):
        parks = []
        # all osm parks at 10/07/2016
        api = overpy.Overpass()
        request = '[timeout:620][date:"2016-07-17T00:00:00Z"];(way["leisure"="park"];way["landuse"="recreation_ground"];way["leisure"="recreation_ground"];way["leisure"="pitch"];way["leisure"="garden"];way["leisure"="golf_course"];way["leisure"="playground"];way["landuse"="meadow"];way["landuse"="grass"];way["landuse"="greenfield"];way["natural"="scrub"];way["natural"="heath"];way["natural"="grassland"];way["landuse"="farmyard"];way["landuse"="vineyard"];way[landuse=farmland];way[landuse=orchard];);out;>;out skel qt;'
        request = '[bbox:{},{},{},{}]{}'.format(south, west, north, east, request)
        response = api.query(request)
        for w in response.ways:

            name = w.tags.get("name", None)
            leisure = w.tags.get("leisure", None)
            landuse = w.tags.get("landuse", None)
            natural = w.tags.get("natural", None)
            if name:
                area_name = name[:1].upper() + name[1:]
            elif leisure:
                area_name = leisure[:1].upper() + leisure[1:]
            elif landuse:
                area_name = landuse[:1].upper() + landuse[1:]
            elif natural:
                area_name = natural[:1].upper() + natural[1:]
            else:
                area_name = 'Error'

            parks.append({
                'id': w.id,
                'name': area_name,
                'coords': [[float(c.lat), float(c.lon)] for c in w.nodes]
                # json.dumps and json.loads
            })
        return parks


    def get_s2_cell_as_polygon(self, lat, lon, level=12):
        cell = s2sphere.Cell(s2sphere.CellId.from_lat_lng(s2sphere.LatLng.from_degrees(lat, lon)).parent(level))
        return [(self.get_vertex(cell, v)) for v in range(0, 4)]


    def get_vertex(self, cell, v):
        vertex = s2sphere.LatLng.from_point(cell.get_vertex(v))
        return (vertex.lat().degrees, vertex.lng().degrees)


    def check_in_park(self, lat, lon):
        try:
            cell = Polygon(self.get_s2_cell_as_polygon(lat, lon, 20))  # s2 lvl 20
            if len(self.PARKS_CACHE) > 0:
                for p in self.PARKS_CACHE:
                    coords = p['coords']
                    # osm polygon can be a line
                    if len(coords) == 2:
                        shape = LineString(coords)
                        if shape.within(cell.centroid):
                            return { 'id' : p['id'], 'internal' : p['internal'], 'name' : p['name'] }
                    if len(coords) > 2:
                        shape = Polygon(coords)
                        if shape.contains(cell.centroid):
                            return {'id': p['id'], 'internal' : p['internal'], 'name': p['name']}
            return None

        except Exception as e:
            self.log.error('Unknown error: in check_in_park: {}',e)
            return None


    def update_gyms(self):
        self.log.info('Updating forts parks in DB.')
        self.PARKS_CACHE.preload()
        try:
            with db.session_scope() as session:
                rs = session.query(db.Fort).all()

                for g in rs:
                    try:
                        park = self.check_in_park(g.lat, g.lon)
                        if park and g.park != park['name']:
                            updated = session.query(db.Fort)\
                                .filter(db.Fort.id == g.id) \
                                .with_for_update() \
                                .update({'park': park['name'], 'parkid' : park['internal']})
                            db.FORT_CACHE.park[g.id] = park['name']
                    except Exception as e:
                        self.log.warning('Moving on next gym. Error while updating a gym park : {}', e)
                session.commit()
        except Exception as e:
            self.log.warning('Error while updating gym parks : {}', e)


class ParksCache:
    """Simple local cache for actual parks

    It's used in order not to make as many queries to the database.
    """

    def __init__(self):
        self.log = get_logger('parks')
        self.store = {}

    def __len__(self):
        return len(self.store)

    def __getitem__(self, index):
        return self.store[index]

    def add(self, park):
        self.store[park['id']] = park

    def remove(self, cache_id):
        try:
            del self.store[cache_id]
        except KeyError:
            pass

    def empty(self):
        self.store = {}

    def __contains__(self, index):
        try:
            park = self.store[index]
            return park['id'] == index
        except KeyError:
            return False

    def __iter__(self):
        return iter(self.store.values())

    def preload(self):
        try:
            if len(self.store) > 0:
                self.store = {}
            with db.session_scope() as session:
                parks = session.query(Park) \
                        .filter(Park.instanceid == db.instance_id)

                for park in parks:
                    obj = {
                        'id': park.id,
                        'internal': park.internalid,
                        'name': park.name,
                        'coords': json.loads(park.coords),
                    }
                    self.add(obj)
                self.log.info("Loaded {} parks for this instance", parks.count())
        except Exception as e:
            self.log.error('Error while preloading parks : {}', e)

