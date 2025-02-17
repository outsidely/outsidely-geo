import geopandas
from shapely.geometry import LineString, Point

step1 = geopandas.GeoSeries([LineString([(0, 0), (1, 10), (0, 20)])]).simplify(.0001).to_json()



print(step2.to_json())