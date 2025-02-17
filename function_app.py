#https://learn.microsoft.com/en-us/python/api/azure-functions/azure.functions?view=azure-python
import azure.functions as func
import logging
import geopandas
import pyogrio
from io import BytesIO
from staticmap import *
from shapely.geometry import LineString
import json
from geographiclib.geodesic import Geodesic
from dateutil import parser
import math

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

def createJsonHttpResponse(statusCode, message):
    return func.HttpResponse('{"statusCode":' + str(statusCode) + ',"message":"' + str(message) + '"}',status_code=statusCode,mimetype="applicaton/json")

# activity data should be in a GeoJSON format with a FeatureCollection of Features with geometry type of Points
# additional info will be pulled from the properties of the Feature such as time, elevation, and more
def parseActivityData(geojson):
    activityData = []
    for feature in geojson["features"]:
        if feature["geometry"]["type"] == "Point":
            properties = {}
            if (feature["properties"]["time"]):
                properties["timestamp"] = feature["properties"]["time"]
            if (feature["properties"]["ele"]):
                properties["elevation"] = feature["properties"]["ele"]
            if (feature["geometry"]["coordinates"][0]):
                properties["longitude"] = feature["geometry"]["coordinates"][0]
            if (feature["geometry"]["coordinates"][1]):
                properties["latitude"] = feature["geometry"]["coordinates"][1]
            activityData.append(properties)
    return activityData

def parseStatisticsData(activityData):

    statisticsData = {}

    min_time = parser.parse(activityData[0]["timestamp"])
    max_time = parser.parse(activityData[len(activityData)-1]["timestamp"])

    time = (max_time - min_time).seconds
    distance = 0.0
    ascent = 0.0
    descent = 0.0

    for i in range(len(activityData)-1):
        if parser.parse(activityData[0]["timestamp"]) > parser.parse(activityData[len(activityData)-1]["timestamp"]):
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

    statisticsData["time"] = time
    statisticsData["distance"] = distance
    statisticsData["ascent"] = ascent
    statisticsData["descent"] = descent

    return statisticsData

#curl "http://localhost:7071/api/uploadActivity" -H "Content-Type: application/gpx+xml" -d "@/home/jesse/Desktop/test.gpx" --output "/home/jesse/Desktop/test.geojson"
@app.route(route="uploadActivity")
def uploadActivity(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called uploadActivity')
    try:
        if (req.headers["Content-Type"] == "application/gpx+xml"):
            request_body = BytesIO(req.get_body())
            data_frame = pyogrio.read_dataframe(request_body, driver="GPX", layer="track_points")
            geojson_out = BytesIO()
            pyogrio.write_dataframe(data_frame, geojson_out, driver="GeoJSON", layer="track_points")
            return func.HttpResponse(geojson_out.getvalue(), status_code=200, mimetype="application/geo+json")
        #https://fitdecode.readthedocs.io/en/latest/
        # if (req.headers["Content-Type"] == "application/vnd.ant.fit "):
        #    fit = True
        else:
            return createJsonHttpResponse(415, "Unsupported Content-Type")
    except:
        return createJsonHttpResponse(500, "Backend Error")

#curl "http://localhost:7071/api/createStaticMap" -H "Content-Type: application/json" -d "@/home/jesse/Desktop/test.geojson" --output "/home/jesse/Desktop/test.png"
@app.route(route="createStaticMap")
def createStaticMap(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called createStaticMap')
    try:
        if (req.headers["Content-Type"] == "application/json"):

            geojson = req.get_json()
            points = []
            for point in parseActivityData(geojson):
                points.append([point["longitude"],point["latitude"]])
            simplified = json.loads(geopandas.GeoSeries([LineString(points)]).simplify(.0001).to_json())
            m = StaticMap(360, 360, padding_x=10, padding_y=10, url_template='http://a.tile.osm.org/{z}/{x}/{y}.png')
            m.add_line(Line(simplified["features"][0]["geometry"]["coordinates"], 'red', 3))
            response_data = BytesIO()
            image = m.render()
            image.save(response_data, format="png")

            return func.HttpResponse(response_data.getvalue(), status_code=200, mimetype="image/png")
        else:
            return createJsonHttpResponse(415, "Unsupported Content-Type")
    except:
        return createJsonHttpResponse(500, "Backend Error")

#curl "http://localhost:7071/api/createStatisticsData" -H "Content-Type: application/json" -d "@/home/jesse/Desktop/test.geojson" --output "/home/jesse/Desktop/test.json"
@app.route(route="createStatisticsData")
def createStatisticsData(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called createStatisticsData')
    try:
        if (req.headers["Content-Type"] == "application/json"):
            body = req.get_json()
            activityData = parseActivityData(body)
            statisticsData = parseStatisticsData(activityData)
            return func.HttpResponse(json.dumps(statisticsData), status_code=200, mimetype="application/json")
        else:
            return createJsonHttpResponse(415, "Unsupported Content-Type")
    except:
        return createJsonHttpResponse(500, "Backend Error")