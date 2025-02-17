import json
from geographiclib.geodesic import Geodesic
from dateutil import parser
import math

def extractActivityData(geojson):
    track_points = []
    for feature in geojson["features"]:
        if feature["geometry"]["type"] == "Point":
            properties = {}
            if (feature["properties"]["time"]):
                properties["time"] = feature["properties"]["time"]
            if (feature["properties"]["ele"]):
                properties["elevation"] = feature["properties"]["ele"]
            if (feature["geometry"]["coordinates"][0]):
                properties["longitude"] = feature["geometry"]["coordinates"][0]
            if (feature["geometry"]["coordinates"][1]):
                properties["latitude"] = feature["geometry"]["coordinates"][1]
            track_points.append(properties)
    return track_points

activityData = None
with open('/home/jesse/Desktop/test4.gpx.geojson') as f:
    f = json.load(f)
    activityData = extractActivityData(f)
print(activityData[0])

# loop through each point
#  keep min time, max time (diff is time)
#  accumulate distance
#  accumulate ascent
min_time = parser.parse(activityData[0]["time"])
max_time = parser.parse(activityData[len(activityData)-1]["time"])
time = (max_time - min_time).seconds
distance = 0.0
ascent = 0.0
descent = 0.0
for i in range(len(activityData)-1):

    if parser.parse(activityData[0]["time"]) > parser.parse(activityData[len(activityData)-1]["time"]):
        raise ValueError("Error: Detected out of order timestamp data")
    
    x1 = activityData[i]["longitude"]
    y1 = activityData[i]["latitude"]
    x2 = activityData[i+1]["longitude"]
    y2 = activityData[i+1]["latitude"]
    
    distance += Geodesic.WGS84.Inverse(y1, x1, y2, x2)['s12']

    if (activityData[i+1]["elevation"] > activityData[i]["elevation"]):
        ascent += activityData[i+1]["elevation"] - activityData[i]["elevation"]
    else:
        descent += activityData[i]["elevation"] - activityData[i+1]["elevation"]

print("time (seconds): " + str(time))
print("distance (meters): " + str(distance))
print("ascent (meters): " + str(ascent))
print("descent (meters): " + str(descent))

speed = (distance/1609.34)/(time/3600)
print("speed (mi/hr): " + str(speed))

pace = (time/60)/(distance/1609.34)
pace_min = str(math.floor((time/60)/(distance/1609.34)))
pace_sec = round((pace - math.floor(pace))*60)
print("pace (min/mi): " + str(str(pace_min) + ":" + str(pace_sec)))