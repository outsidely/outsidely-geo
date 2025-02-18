#https://learn.microsoft.com/en-us/python/api/azure-functions/azure.functions?view=azure-python
#  reference

#https://stackoverflow.com/questions/47068504/where-to-find-python-implementation-of-chaikins-corner-cutting-algorithm
#  useful for smoothing distance

#https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.CubicSpline.html#scipy.interpolate.CubicSpline
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
import os
from azure.data.tables import TableServiceClient, TableClient
import datetime

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

def createJsonHttpResponse(statusCode, message, properties = {}):
    response = {}
    response["statusCode"] = statusCode
    response["message"] = message
    for k,v in properties.items():
        if (k in ["statusCode", "message"]):
            raise Exception("Properties cannot be named statusCode or message")
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
                raise Exception("Error: Detected out of order timestamp data")
            try:
                if (feature["properties"]["time"]):
                    properties["timestamp"] = feature["properties"]["time"]
                if (feature["geometry"]["coordinates"][0]):
                    properties["longitude"] = feature["geometry"]["coordinates"][0]
                if (feature["geometry"]["coordinates"][1]):
                    properties["latitude"] = feature["geometry"]["coordinates"][1]
            except:
                raise Exception("Could not parse timestamp, longitude, or latitude which are required")
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

def saveBlob(data, name):
    blob_service_client = BlobServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    blob_client = blob_service_client.get_blob_client("outsidelycontainer",name)
    blob_client.upload_blob(data)

def upsertEntity(table, entity):
    try:
        partitionKey = entity["PartitionKey"]
        rowkey = entity["RowKey"]
    except:
        raise Exception("PartitionKey and RowKey are required for entities")
    table_service_client = TableServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    table_client = table_service_client.get_table_client(table)
    table_client.upsert_entity(entity)

def queryEntities(table, filter, sortProperty = "", sortReverse=None):
    table_service_client = TableServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    table_client = table_service_client.get_table_client(table)
    entities = table_client.query_entities(filter)
    response = []
    for entity in entities:
        entity["timestamp"] = entity.metadata["timestamp"].isoformat()
        response.append(entity)
    if sortReverse != None:
        response.sort(key=lambda s: s[sortProperty], reverse=sortReverse)
    return response


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

    try:

        activityId = str(uuid.uuid4())
        upsertEntity("activities", {
            "PartitionKey": "userId",
            "RowKey": activityId,
        })

        if (req.headers["Content-Type"] == "application/gpx+xml"):

            # convert to geojson
            request_body = BytesIO(req.get_body())
            data_frame = pyogrio.read_dataframe(request_body, layer="track_points")
            geojson_out = BytesIO()
            pyogrio.write_dataframe(data_frame, geojson_out, driver="GeoJSON", layer="track_points")

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

            # save file, geojson, activityData, preview to storage container
            saveBlob(request_body, activityId + "/source.gpx")
            saveBlob(geojson_out, activityId + "/geojson.json")
            saveBlob(json.dumps(activityData).encode(), activityId + "/activityData.json")
            saveBlob(response_data.getvalue(), activityId + "/preview.png")

            # save statistics + staticmap to tblsvc
            upsertEntity("activities", {
                "PartitionKey": "userId",
                "RowKey": activityId,
                "time": statisticsData["time"],
                "distance": statisticsData["distance"],
                "ascent": statisticsData["ascent"],
                "descent": statisticsData["descent"]
            })

            # return 
            return createJsonHttpResponse(201, "Successfully created activity", {"activityId": activityId})
        
        else:
            return createJsonHttpResponse(415, "Unsupported Content-Type")
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="activities", methods=[func.HttpMethod.GET])
def activities(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called activities')

    try:

        filter = "Timestamp ge datetime'" + (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ') + "'"
        response = queryEntities("activities", filter, "timestamp", True)

        # return 
        return func.HttpResponse(json.dumps(response), status_code=200, mimetype="application/json")

    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))