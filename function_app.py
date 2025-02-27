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
import time
import geopandas
import pyogrio
import json
import uuid
import base64
import hashlib
import secrets
import string
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

def createJsonHttpResponse(statuscode, message, properties = {}, headers = {}):
    response = {}
    response["statuscode"] = statuscode
    response["message"] = message
    for k,v in properties.items():
        if (k in ["statuscode", "message"]):
            raise Exception("Properties cannot be named statuscode or message")
        else:
            response[k] = v
    return func.HttpResponse(json.dumps(response), status_code=statuscode, mimetype="application/json", headers=headers)

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

def queryEntities(table, filter, properties = None, aliases = {}, sortproperty = None, sortreverse=False):
    table_service_client = TableServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    table_client = table_service_client.get_table_client(table)
    entities = table_client.query_entities(filter, select=properties)
    if properties == None:
        properties = []
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

def tsUnixToIso(ts):
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%SZ')

def validateData(validationtype, value):
    eq = queryEntities("validations","PartitionKey eq '" + validationtype + "' and RowKey eq '" + value + "'")
    if len(eq) == 0:
        return False
    else:
        return True

def authorizer(req):
    try:
        authorized = False
        parts = base64.b64decode(req.headers.get("Authorization").replace("Basic ", "")).decode().split(":")
        userid = parts[0]
        password = parts[1]
        qe = queryEntities("users", "PartitionKey eq '" + userid + "' and RowKey eq 'account'", ["salt", "password"])
        if len(qe) > 0:
            salt = qe[0]["salt"]
            if hashlib.sha512(str(salt + password).encode()).hexdigest() == qe[0]["password"]:
                authorized = True
    except:
        authorized = False
        userid = ""
    return {"authorized": authorized, "userid": userid}

#curl "http://localhost:7071/api/upload" -F upload="@/home/jesse/Downloads/Something_different.gpx" -F userid=jamund -F password=EZmnFTuQPVnCydWCuJVbHpcS5vZvSjKq -F activitytype=Other --output -
@app.route(route="upload", methods=[func.HttpMethod.POST])
def upload(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called upload')

    try:

        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "Unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})

        activityid = str(uuid.uuid4())

        upload = None
        try:
            upload = req.files["upload"].stream.read()
        except:
            return createJsonHttpResponse(400, "Missing upload data of activity (GPX file)")

        activityproperties = {}

        try:
            activityproperties["activitytype"] = req.form.get("activitytype")
            if not validateData("activitytype", activityproperties["activitytype"]):
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

        # create clean track file
        points = []
        for point in activitydata:
            points.append([point["longitude"],point["latitude"]])
        route = geopandas.GeoSeries([LineString(points)])
        routejson = json.loads(route.to_json())

        # create preview
        routejsonsimplified = json.loads(route.simplify(.0001).to_json())
        m = StaticMap(360, 360, padding_x=10, padding_y=10, url_template='http://a.tile.osm.org/{z}/{x}/{y}.png')
        m.add_line(Line(routejsonsimplified["features"][0]["geometry"]["coordinates"], 'red', 3))
        preview = BytesIO()
        image = m.render()
        image.save(preview, format="png")

        # save file, geojson, activityData, preview to storage container
        saveBlob(upload, activityid + "/source.gpx", "application/gpx+xml")
        saveBlob(json.dumps(routejson).encode(), activityid + "/geojson.json", "application/json")
        saveBlob(json.dumps(activitydata).encode(), activityid + "/activityData.json", "application/json")
        saveBlob(preview.getvalue(), activityid + "/preview.png", "image/png")

        # capture information
        properties_capture = ["name", "description"]
        formdict = req.form.to_dict()
        for k in formdict.keys():
            if k in properties_capture:
                activityproperties[k] = formdict[k]
        activityproperties["PartitionKey"] = auth["userid"]
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

        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "Unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})

        feedresponse = True
        filter = ""

        if "activityid" in req.params.keys() and "userid" not in req.params.keys():
            return createJsonHttpResponse(400, "activityid must be accompanied by a userid")
        elif "activityid" in req.params.keys() and "userid" in req.params.keys():
            feedresponse = False
            filter +=  "PartitionKey eq '" + req.params.get("userid") + "'" + " and RowKey eq '" + req.params.get("activityid") + "'"
        else:
            delta = 86400*7
            endtime = 0
            starttime = 0
            if "endtime" in req.params.keys() and "starttime" in req.params.keys():
                endtime = int(req.params.get("endtime"))
                starttime = int(req.params.get("starttime"))
                if (endtime - starttime > delta):
                    raise Exception("Maximum time delta of " + str(delta) + " for activities")
            else:
                endtime = int(time.time())
                starttime = int(endtime - delta)
            filter += "Timestamp le datetime'" + tsUnixToIso(endtime) + "' and Timestamp ge datetime'" + tsUnixToIso(starttime) + "'"
            if "userid" in req.params.keys():
                filter += " and PartitionKey eq '" + req.params.get("userid") + "'"

        activities = queryEntities("activities", filter, aliases={"PartitionKey": "userid", "RowKey": "activityid"}, sortproperty="timestamp", sortreverse=True)
        
        for a in activities:
            a["previewurl"] = "data?datatype=preview&activityid=" + a["activityid"]
            userdata = queryEntities("users","PartitionKey eq '" + a["userid"] + "' and RowKey eq 'account'")
            if len(userdata) > 0:
                a["firstname"] = userdata[0]["firstname"]
                a["lastname"] = userdata[0]["lastname"]
        
        response = {"activities": activities}
        if feedresponse:
            nexturl = "activities?endtime=" +str(starttime) + "&starttime=" + str(starttime - delta)
            if "userid" in req.params.keys():
                nexturl += "&userid=" + req.params.get("userid")
            response["nexturl"] = nexturl

        return func.HttpResponse(json.dumps(response), status_code=200, mimetype="application/json")

    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))
    
@app.route(route="data", methods=[func.HttpMethod.GET])
def data(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called data')

    try:

        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "Unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})

        if "datatype" not in req.params.keys():
            return createJsonHttpResponse(400, "datatype required")
        
        datatype = req.params.get("datatype")

        if not validateData("datatype", datatype):
            return createJsonHttpResponse(400, "datatype invalid")

        match datatype:
            case "preview":
                if "activityid" not in req.params.keys():
                    return createJsonHttpResponse(400, "activityid required")
                getblob = getBlob(req.params.get("activityid") + "/preview.png")
            case "geojson":
                if "activityid" not in req.params.keys():
                    return createJsonHttpResponse(400, "activityid required")
                getblob = getBlob(req.params.get("activityid") + "/geojson.json")
            case _:
                return createJsonHttpResponse(400, "invalid datatype")

        return func.HttpResponse(getblob["data"], status_code=200, mimetype=getblob["contenttype"])
    
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="validations", methods=[func.HttpMethod.GET])
def validations(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called validations')

    auth = authorizer(req)
    if not auth["authorized"]:
        return createJsonHttpResponse(401, "Unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})

    try:
        
        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "Unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})
        
        if "validationtype" not in req.params.keys():
            return createJsonHttpResponse(400, "validationtype parameter required")
        
        data = queryEntities("validations", "PartitionKey eq '" + req.params.get("validationtype") + "'",["RowKey","label","sort"],{"RowKey": req.params["validationtype"]}, "sort")

        return func.HttpResponse(json.dumps(data), status_code=200, mimetype="application/json")
    
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))