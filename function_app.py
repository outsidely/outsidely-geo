#https://learn.microsoft.com/en-us/python/api/azure-functions/azure.functions?view=azure-python
#  reference

#https://stackoverflow.com/questions/47068504/where-to-find-python-implementation-of-chaikins-corner-cutting-algorithm
#  useful for smoothing distance

#https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.CubicSpline.html#scipy.interpolate.CubicSpline
#  useful for smoothing elevation

#https://fitdecode.readthedocs.io/en/latest/
#  useful for reading fit files

import logging
import os
import datetime
import math
import geopandas
import pyogrio
import json
import uuid
import azure.functions as func
from io import BytesIO
from dateutil import parser
from staticmap import *
from shapely.geometry import LineString
from geographiclib.geodesic import Geodesic
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, BlobClient, ContentSettings
from azure.data.tables import TableServiceClient, TableClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

def createJsonHttpResponse(statuscode, message, properties = {}):
    response = {}
    response["statuscode"] = statuscode
    response["message"] = message
    for k,v in properties.items():
        if (k in ["statuscode", "message"]):
            raise Exception("Properties cannot be named statuscode or message")
        else:
            response[k] = v
    return func.HttpResponse(json.dumps(response), status_code=statuscode, mimetype="application/json")

# should ensure the output is good: everything has timestamp, longitude, latitude, timestamp is in order, longitude and latitude values are in domain
def parseActivityData(geojson):
    activitydata = []
    priortimestamp = parser.parse("2020-01-01T00:00:00+00:00")
    currenttimestamp = None
    for feature in geojson["features"]:
        if feature["geometry"]["type"] == "Point":
            properties = {}
            currenttimestamp = parser.parse(feature["properties"]["time"])
            if priortimestamp != "" and priortimestamp > currenttimestamp:
                raise Exception("Error: Detected out of order timestamp data")
            priortimestamp = currenttimestamp
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
            activitydata.append(properties)
    return activitydata

def parseStatisticsData(activitydata):

    statisticsdata = {}

    mintime = parser.parse(activitydata[0]["timestamp"])
    maxtime = parser.parse(activitydata[len(activitydata)-1]["timestamp"])

    time = (maxtime - mintime).seconds
    distance = 0.0
    ascent = 0.0
    descent = 0.0

    for i in range(len(activitydata)-1):
        x1 = activitydata[i]["longitude"]
        y1 = activitydata[i]["latitude"]
        x2 = activitydata[i+1]["longitude"]
        y2 = activitydata[i+1]["latitude"]
        distance += Geodesic.WGS84.Inverse(y1, x1, y2, x2)['s12']
        if (activitydata[i+1]["elevation"] > activitydata[i]["elevation"]):
            ascent += activitydata[i+1]["elevation"] - activitydata[i]["elevation"]
        else:
            descent += activitydata[i]["elevation"] - activitydata[i+1]["elevation"]

    statisticsdata["starttime"] = mintime
    statisticsdata["time"] = time
    statisticsdata["distance"] = distance
    statisticsdata["ascent"] = ascent
    statisticsdata["descent"] = descent

    return statisticsdata

def saveBlob(data, name, contenttype = None):
    blobserviceclient = BlobServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    blobclient = blobserviceclient.get_blob_client(os.environ["storagecontainer"], name)
    if (contenttype != None):
        content_settings = ContentSettings(content_type=contenttype)
        blobclient.upload_blob(data, overwrite=True, content_settings=content_settings)
    else:
        blobclient.upload_blob(data, overwrite=True)

def getBlob(name):
    blobserviceclient = BlobServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    blobclient = blobserviceclient.get_blob_client(os.environ["storagecontainer"], name)
    blob = blobclient.download_blob()
    data = BytesIO()
    data = blob.readall()
    return {"data": data, "contenttype": blob.properties.content_settings["content_type"]}

def upsertEntity(table, entity):
    try:
        partitionKey = entity["PartitionKey"]
        rowkey = entity["RowKey"]
    except:
        raise Exception("PartitionKey and RowKey are required for entities")
    tableserviceclient = TableServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    tableclient = tableserviceclient.get_table_client(table)
    tableclient.upsert_entity(entity)

def queryEntities(table, filter, properties = [], aliases = {}, sortproperty = None, sortreverse=False):
    table_service_client = TableServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    table_client = table_service_client.get_table_client(table)
    entities = table_client.query_entities(filter)
    response = []
    for entity in entities:
        currentity = {}
        if (len(properties)>0 and "timestamp" in properties) or len(properties)==0:
            currentity["timestamp"] = entity.metadata["timestamp"].isoformat()
        for p in entity:
            if (len(properties)>0 and p in properties) or len(properties)==0:
                if "TablesEntityDatetime" in str(type(entity[p])):
                    currentity[p] = entity[p].isoformat()
                else:
                    currentity[p] = entity[p]
        for a in aliases:
            currentity[aliases[a]] = currentity.pop(a)
        response.append(currentity)
    if sortproperty != None:
        try:
            response.sort(key=lambda s: s[sortproperty], reverse=sortreverse)
        except:
            raise Exception("Error in sorting, likely due to missing property in response or entity")
    return response

#curl "http://localhost:7071/api/upload" -F upload="@/home/jesse/Downloads/Something_different.gpx" -F userid=Jesse -F activitytype=Other --output -
@app.route(route="upload", methods=[func.HttpMethod.POST])
def upload(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called upload')

    try:

        # validate data request at some point here before proceeding
        userid = None
        activityid = str(uuid.uuid4())

        upload = None
        try:
            upload = req.files["upload"].stream.read()
        except:
            return createJsonHttpResponse(400, "Missing upload data of activity (GPX file)")

        activityproperties = {}
        try:
            userid = req.form["userid"]
        except:
            return createJsonHttpResponse(400, "Missing required field userid")
        try:
            activityproperties["activitytype"] = req.form["activitytype"]
            activitytypes = queryEntities("validations", "PartitionKey eq 'activitytype'", aliases={"RowKey": "activitytype"})
            activitytypefound = False
            for at in activitytypes:
                if at["activitytype"] == activityproperties["activitytype"]:
                    activitytypefound = True
            if not activitytypefound:
                raise
        except:
            return createJsonHttpResponse(400, "Missing or invalid activitytype")

        # convert to geojson
        dataframe = pyogrio.read_dataframe(upload, layer="track_points")
        geojson = BytesIO()
        pyogrio.write_dataframe(dataframe, geojson, driver="GeoJSON", layer="track_points")

        # convert to activityModel
        activitydata = parseActivityData(json.loads(geojson.getvalue().decode()))
        
        # calculate statistics
        statisticsdata = parseStatisticsData(activitydata)

        # create preview
        points = []
        for point in activitydata:
            points.append([point["longitude"],point["latitude"]])
        simplified = json.loads(geopandas.GeoSeries([LineString(points)]).simplify(.0001).to_json())
        m = StaticMap(360, 360, padding_x=10, padding_y=10, url_template='http://a.tile.osm.org/{z}/{x}/{y}.png')
        m.add_line(Line(simplified["features"][0]["geometry"]["coordinates"], 'red', 3))
        preview = BytesIO()
        image = m.render()
        image.save(preview, format="png")

        # save file, geojson, activityData, preview to storage container
        saveBlob(upload, activityid + "/source.gpx", "application/gpx+xml")
        saveBlob(geojson, activityid + "/geojson.json", "application/json")
        saveBlob(json.dumps(activitydata).encode(), activityid + "/activityData.json", "application/json")
        saveBlob(preview.getvalue(), activityid + "/preview.png", "image/png")

        # capture information
        properties_capture = ["name", "description"]
        formdict = req.form.to_dict()
        for k in formdict.keys():
            if k in properties_capture:
                activityproperties[k] = formdict[k]
        activityproperties["PartitionKey"] = userid
        activityproperties["RowKey"] = activityid
        activityproperties["time"] = statisticsdata["time"]
        activityproperties["distance"] = statisticsdata["distance"]
        activityproperties["ascent"] = statisticsdata["ascent"]
        activityproperties["descent"] = statisticsdata["descent"]
        activityproperties["starttime"] = statisticsdata["starttime"]

        # save statistics to tblsvc
        upsertEntity("activities", activityproperties)

        return createJsonHttpResponse(201, "Successfully created activity", {"activityid": activityid})

    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="activities", methods=[func.HttpMethod.GET])
def activities(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called activities')

    try:

        filter = "Timestamp ge datetime'" + (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ') + "'"
        response = queryEntities("activities",filter, aliases={"PartitionKey": "userid", "RowKey": "activityid"}, sortproperty="timestamp", sortreverse=True)
        for a in response:
            a["previewurl"] = "preview/" + a["activityid"]

        return func.HttpResponse(json.dumps(response), status_code=200, mimetype="application/json")

    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="preview/{activityid}", methods=[func.HttpMethod.GET])
def preview(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called preview')

    try:
        getblob = getBlob(req.route_params.get("activityid") + "/preview.png")
        return func.HttpResponse(getblob["data"], status_code=200, mimetype=getblob["contenttype"])
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="validations/{validationtype}", methods=[func.HttpMethod.GET])
def validations(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called validations')

    try:
        data = queryEntities("validations", "PartitionKey eq '" + req.route_params.get("validationtype") + "'",["RowKey","label","sort"],{"RowKey": "activitytype"}, "sort")
        return func.HttpResponse(json.dumps(data), status_code=200, mimetype="application/json")
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))