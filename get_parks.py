import overpy
from shapely.geometry import Polygon, Point, LineString
import s2sphere
from monocle import db, sanitized as conf
from monocle.web_utils import get_vertex
from monocle.bounds import north, south, east, west


def get_all_parks():
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
            'type': 'park',
            'name': area_name,
            'coords': [[float(c.lat), float(c.lon)] for c in w.nodes]
        })
    return parks

def get_s2_cell_as_polygon(lat, lon, level=12):
    cell = s2sphere.Cell(s2sphere.CellId.from_lat_lng(s2sphere.LatLng.from_degrees(lat, lon)).parent(level))
    return [(get_vertex(cell, v)) for v in range(0, 4)]

def get_vertex(cell, v):
    vertex = s2sphere.LatLng.from_point(cell.get_vertex(v))
    return (vertex.lat().degrees, vertex.lng().degrees)

with db.session_scope() as ses:
    rs = ses.query(db.Fort).all()
    gyms = []
    parks = get_all_parks()

    for g in rs:
        gym_point = Point(g.lat, g.lon)
        cell = Polygon(get_s2_cell_as_polygon(g.lat, g.lon, 20)) # s2 lvl 20
        for p in parks:
            coords = p['coords']
            # osm polygon can be a line
            if len(coords) == 2:
                shape = LineString(coords)
                if shape.within(gym_point) or cell.intersects(shape):
                    ses.query(db.Fort).filter(db.Fort.id == g.id).update({'park': p['name']})
                    gyms.append(g)
                    break
            if len(coords) > 2:
                shape = Polygon(coords)
                if shape.contains(gym_point) or cell.intersects(shape):
                    ses.query(db.Fort).filter(db.Fort.id == g.id).update({'park': p['name']})
                    gyms.append(g)
                    break
    ses.commit()   