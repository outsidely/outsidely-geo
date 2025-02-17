#https://learn.microsoft.com/en-us/python/api/azure-functions/azure.functions?view=azure-python
#  reference

#https://stackoverflow.com/questions/47068504/where-to-find-python-implementation-of-chaikins-corner-cutting-algorithm
#  useful for smoothing distance

#https://en.wikipedia.org/wiki/Spline_interpolation
#  useful for smoothing elevation

#https://fitdecode.readthedocs.io/en/latest/
#  useful for reading fit files

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
import uuid
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

def createJsonHttpResponse(statusCode, message, properties = {}):
    response = {}
    response["statusCode"] = statusCode
    response["message"] = message
    for k,v in properties.items():
        if (k not in ["statusCode", "message"]):
            raise ValueError("Properties cannot be named statusCode or message")
        else:
            response[k] = v
    return func.HttpResponse(json.dumps(response), status_code=statusCode, mimetype="applicaton/json")

# should ensure the output is good: everything has timestamp, longitude, latitude, timestamp is in order, longitude and latitude values are in domain
def parseActivityData(geojson):
    activityData = []
    prior_timestamp = ""
    for feature in geojson["features"]:
        if feature["geometry"]["type"] == "Point":
            properties = {}
            if prior_timestamp != "" and parser.parse(prior_timestamp) > parser.parse(feature["properties"]["time"]):
                raise ValueError("Error: Detected out of order timestamp data")
            try:
                if (feature["properties"]["time"]):
                    properties["timestamp"] = feature["properties"]["time"]
                if (feature["geometry"]["coordinates"][0]):
                    properties["longitude"] = feature["geometry"]["coordinates"][0]
                if (feature["geometry"]["coordinates"][1]):
                    properties["latitude"] = feature["geometry"]["coordinates"][1]
            except:
                raise ValueError("Could not parse timestamp, longitude, or latitude which are required")
            try:
                properties["elevation"] = feature["properties"]["ele"]
            except:
                ex = True
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

#curl "http://localhost:7071/api/uploadActivityTest" -H "Content-Type: application/gpx+xml" -d "@/home/jesse/Desktop/test.gpx" --output "/home/jesse/Desktop/test.geojson"
@app.route(route="uploadActivityTest")
def uploadActivityTest(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called uploadActivityTest')
    try:
        if (req.headers["Content-Type"] == "application/gpx+xml"):
            request_body = BytesIO(req.get_body())
            data_frame = pyogrio.read_dataframe(request_body, layer="track_points")
            geojson_out = BytesIO()
            pyogrio.write_dataframe(data_frame, geojson_out, driver="GeoJSON", layer="track_points")
            return func.HttpResponse(geojson_out.getvalue(), status_code=200, mimetype="application/geo+json")
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
    
#curl "http://localhost:7071/api/uploadActivity" -H "Content-Type: application/gpx+xml" -d "@/home/jesse/Desktop/test.gpx" --output -
@app.route(route="uploadActivity", methods=[func.HttpMethod.POST])
def uploadActivity(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called uploadActivity')

    activityId = str(uuid.uuid4())

    try:
        if (req.headers["Content-Type"] == "application/gpx+xml"):

            # convert to geojson
            request_body = BytesIO(req.get_body())
            data_frame = pyogrio.read_dataframe(request_body, layer="track_points")
            geojson_out = BytesIO()
            pyogrio.write_dataframe(data_frame, geojson_out, driver="GeoJSON", layer="track_points")
            #return func.HttpResponse(geojson_out.getvalue(), status_code=200, mimetype="application/geo+json")

            # convert to activityModel
            activityData = parseActivityData(json.loads(geojson_out.getvalue().decode()))
            
            # calculate statistics
            statisticsData = parseStatisticsData(activityData)

            # create static map
            points = []
            for point in activityData:
                points.append([point["longitude"],point["latitude"]])
            simplified = json.loads(geopandas.GeoSeries([LineString(points)]).simplify(.0001).to_json())
            m = StaticMap(360, 360, padding_x=10, padding_y=10, url_template='http://a.tile.osm.org/{z}/{x}/{y}.png')
            m.add_line(Line(simplified["features"][0]["geometry"]["coordinates"], 'red', 3))
            response_data = BytesIO()
            image = m.render()
            image.save(response_data, format="png")

            # save file, geojson, activitymodel to storage container

            # save statistics + staticmap to tblsvc
            
            # return 
            return createJsonHttpResponse(200, "Successfully processed activity", {"activityId": activityId})
        
        else:
            return createJsonHttpResponse(415, "Unsupported Content-Type")
    except:
        return createJsonHttpResponse(500, "Backend Error")