import logging
import os
import datetime
import pytz
import time
import geopandas
import pyogrio
import json
import uuid
import base64
import hashlib
import secrets
import string
import math
import azure.functions as func
from io import BytesIO
from dateutil import parser
from staticmap import *
from shapely.geometry import LineString
from geographiclib.geodesic import Geodesic
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, BlobClient, ContentSettings
from azure.data.tables import TableServiceClient, TableClient, UpdateMode
from PIL import Image

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
    return {"version": 1, "data": activitydata}

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

    statisticsdata["version"] = 1

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
    try:
        blobserviceclient = BlobServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
        blobclient = blobserviceclient.get_blob_client(os.environ["storagecontainer"], name)
        blob = blobclient.download_blob()
        data = BytesIO()
        data = blob.readall()
        return {"data": data, "contenttype": blob.properties.content_settings["content_type"], "status": True}
    except:
        return {"data": None, "contenttype": None, "status": False}

def deleteBlob(name):
    try:
        blobserviceclient = BlobServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
        blobclient = blobserviceclient.get_blob_client(os.environ["storagecontainer"], name)
        blobclient.delete_blob()
    except:
        return False
    return True

def listBlobs(startswith):
    blobserviceclient = BlobServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    containerclient = blobserviceclient.get_container_client(os.environ["storagecontainer"])
    blobs = containerclient.list_blobs(startswith)
    bloblist = []
    for b in blobs:
        bloblist.append(b)
    return bloblist

def upsertEntity(table, entity):
    try:
        partitionKey = entity["PartitionKey"]
        rowkey = entity["RowKey"]
    except:
        raise Exception("PartitionKey and RowKey are required for entities")
    tableserviceclient = TableServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    tableclient = tableserviceclient.get_table_client(table)
    tableclient.upsert_entity(entity)

def deleteEntity(table, partitionkey, rowkey):
    tableserviceclient = TableServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    tableclient = tableserviceclient.get_table_client(table)
    tableclient.delete_entity(partitionkey, rowkey)

def queryEntities(table, filter, properties = None, aliases = {}, sortproperty = None, sortreverse=False, userid=None, connectionproperty=None):
    table_service_client = TableServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    table_client = table_service_client.get_table_client(table)

    if (userid==None and connectionproperty != None) or (userid!=None and connectionproperty == None):
        raise Exception("userid and connectionproperty are both required if one is provided")

    # if connections are provided, then build successive calls with up to 10 checked in each
    allentities = []
    if connectionproperty != None:
        connections = [userid]
        table_client_connections = table_service_client.get_table_client("connections")
        for entity in table_client_connections.query_entities("PartitionKey eq '" + userid + "' and connectiontype eq 'connected'", select=["RowKey"]):
            connections.append(entity["RowKey"])
        for connectionbatch in splitList(connections, 10):
            filteradd = ""
            if len(filter) != 0:
                filteradd = " and "
            filteradd += "("
            first = True
            for cb in connectionbatch:
                if not first:
                    filteradd += " or "
                first = False
                filteradd += " " + connectionproperty + " eq '" + cb + "'"
            filteradd += ")"
            allentities.append(table_client.query_entities(filter + filteradd, select=properties))
    else:
        allentities.append(table_client.query_entities(filter, select=properties))

    if properties == None:
        properties = []
    response = []
    for entities in allentities:
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
    if sortproperty != None and len(allentities)>0:
        try:
            response.sort(key=lambda s: s[sortproperty], reverse=sortreverse)
        except:
            raise Exception("Error in sorting, likely due to missing property in response or entity")
    return response

def splitList(list, size):
    for i in range(0, len(list), size):
        yield list[i:i + size]

def incrementDecrement(table, partitionkey, rowkey, property, value, integer):
    entity = queryEntities(table, "PartitionKey eq '" + partitionkey + "' and RowKey eq '" + rowkey + "'", [property])
    if len(entity) == 0:
        raise Exception("entity not found")
    if not integer:
        try:
            currvalue = float(entity[0][property])
        except:
            currvalue = float(0)
    else:
        try:
            currvalue = int(entity[0][property])
        except:
            currvalue = int(0)
    newvalue = currvalue + value
    if newvalue < 0:
        if not integer:
            newvalue = float(0)
        else:
            newvalue = int(0)
    upsertEntity(table, {
        "PartitionKey": partitionkey,
        "RowKey": rowkey,
        property: newvalue
    })

def tsUnixToIso(ts):
    return datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%SZ')

def validateData(validationtype, value):
    qe = queryEntities("validate","PartitionKey eq '" + validationtype + "' and RowKey eq '" + value + "'")
    if len(qe) == 0:
        return {"status": False, "label": "NoLabel"}
    else:
        return {"status": True, "label": qe[0]["label"]}

def authorizer(req):
    try:
        authorized = False
        parts = base64.b64decode(req.headers.get("Authorization").replace("Basic ", "")).decode().split(":")
        userid = parts[0]
        password = parts[1]
        qe = queryEntities("users", "PartitionKey eq '" + userid + "' and RowKey eq 'account'", ["salt", "password", "unitsystem", "timezone"])
        if len(qe) > 0:
            salt = qe[0]["salt"]
            if hashlib.sha512(str(salt + password).encode()).hexdigest() == qe[0]["password"]:
                authorized = True
            unitsystem = qe[0].get("unitsystem", "metric")
            timezone = qe[0].get("timezone", "US/Eastern")
    except:
        authorized = False
        userid = ""
        unitsystem = "metric"
        timezone = "US/Eastern"
    return {"authorized": authorized, "userid": "mamund", "unitsystem": unitsystem, "timezone": timezone}

def checkJsonProperties(json, properties):
    matched = []
    missing = []
    invalid = []
    propertynames = []
    status = True
    message = ""
    for pn in properties:
        propertynames.append(pn["name"])
    for k in json.keys():
        if k in propertynames:
            matched.append(k)
    for p in properties:
        if p.get("required",False) and p["name"] not in json.keys():
            missing.append(p["name"])
    for k in json.keys():
        if k not in propertynames:
            invalid.append(k)
    if len(missing) > 0:
        status = False
        message = "missing required properties: " + ", ".join(missing)  + "."
    if len(invalid) > 0:
        status = False
        if len(message) > 0:
            message += " "
        message += "invalid properties: " + ", ".join(invalid)  + "."
    if len(matched) == 0:
        status = False
        message = "no properties matched."
    for p in properties:
        if p.get("validate", False) and p["name"] in matched:
            if not validateData(p["name"], json[p["name"]])["status"]:
                status = False
                if len(message) > 0:
                    message += " "
                message += "invalid " + p["name"] + ": " + json[p["name"]] + "."
    return {"missing": missing, "invalid": invalid, "status": status, "message": message}

def launderUnits(unitsystem, unittype, in_distance = None, in_time = None):
    # time (hh:mm:ss)
    # distance (km) (mi)
    # ascent / descent (m) (ft)
    # speed (km/hr) (mi/hr)
    # pace min/km (min/mi)
    if unittype == "time":
        if in_time >= 3600:
            return time.strftime('%Hh %Mm', time.gmtime(in_time))
        else:
            return time.strftime('%Mm %Ss', time.gmtime(in_time))
    if unitsystem == "metric":
        match unittype:
            case "distance":
                return f"{in_distance/1000:,.2f}" + " km"
            case "ascent":
                return f"{in_distance:,.0f}" + " m"
            case "speed":
                return f"{(in_distance/1000)/(in_time/3600):,.1f}" + " km/hr"
            case "pace":
                pvalue = (in_time/60)/(in_distance/1000)
                return str(math.floor(pvalue)) + ":" + (f"{(pvalue - math.floor(pvalue))*60:.0f}").zfill(2) + " min/km"
    elif unitsystem == "imperial":
        match unittype:
            case "distance":
                return f"{in_distance/1609.34:,.2f}" + " mi"
            case "ascent":
                return f"{in_distance*3.28084:,.0f}" + " ft"
            case "speed":
                return f"{(in_distance/1609.34)/(in_time/3600):,.1f}" + " mi/hr"
            case "pace":
                pvalue = (in_time/60)/(in_distance/1609.34)
                return str(math.floor(pvalue)) + ":" + (f"{(pvalue - math.floor(pvalue))*60:.0f}").zfill(2) + " min/mi"
    return ""

def launderTimezone(timestamp, timezone):
    utctime = parser.isoparse(timestamp)
    tztime = utctime.astimezone(pytz.timezone(timezone))
    formattime = tztime.strftime("%B %d at %I:%M %p")
    return formattime

def resizeImage(img, size, quality):
    newimg = Image.open(img)
    newimg.thumbnail(size)
    outimg = BytesIO()
    newimg.save(outimg, optimize=True, quality=quality, format="JPEG")
    return outimg.getvalue()

def useridExists(userid):
    if len(queryEntities("users", "PartitionKey eq '" + userid + "' and RowKey eq 'account'"))>0:
        return True
    else:
        return False

def useridIsConnection(userid, connectionuserid):
    if userid == connectionuserid:
        return True
    if len(queryEntities("connections", "PartitionKey eq '" + userid + "' and RowKey eq '" + connectionuserid + "' and connectiontype eq 'connected"))>0:
        return True
    else:
        return False

@app.route(route="whoami", methods=[func.HttpMethod.GET])
def whoami(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called whoami')
    try:
        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})
        return func.HttpResponse(json.dumps({"userid":auth["userid"]}), status_code=200, mimetype="application/json")
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="upload/activity", methods=[func.HttpMethod.POST])
def uploadactivity(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called uploadactivity')

    try:

        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})

        activityid = str(uuid.uuid4())

        upload = None
        try:
            upload = req.files["upload"].stream.read()
        except:
            return createJsonHttpResponse(400, "missing upload data of activity (GPX file)")
        
        activityproperties = {}
        activityproperties["activitytype"] = req.form.get("activitytype")
        if not validateData("activitytype", activityproperties["activitytype"])["status"]:
            createJsonHttpResponse(400, "invalid or missing activitytype")

        # validate gearid
        gearid = str(req.form.get("gearid") or "")
        if len(gearid) > 0:
            gearentity = queryEntities("gear", "PartitionKey eq '" + auth["userid"] + "' and RowKey eq '" + gearid + "' and retired eq '0' and activitytype eq '" + activityproperties["activitytype"] + "'")
            if len(gearentity) != 1:
                return createJsonHttpResponse(400, "invalid gearid")
            activityproperties["gearid"] = gearid

        # convert to geojson
        dataframe = pyogrio.read_dataframe(upload, layer="track_points")
        geojson = BytesIO()
        pyogrio.write_dataframe(dataframe, geojson, driver="GeoJSON", layer="track_points")

        # convert to activityModel
        activitydata = parseActivityData(json.loads(geojson.getvalue().decode()))
        
        # calculate statistics
        statisticsdata = parseStatisticsData(activitydata["data"])

        # create clean track file
        points = []
        for point in activitydata["data"]:
            points.append([point["longitude"],point["latitude"]])
        route = geopandas.GeoSeries([LineString(points)])
        routejson = json.loads(route.to_json())

        # create preview
        routejsonsimplified = json.loads(route.simplify(.0001).to_json())
        m = StaticMap(300, 300, padding_x=10, padding_y=10, url_template='http://a.tile.osm.org/{z}/{x}/{y}.png')
        m.add_line(Line(routejsonsimplified["features"][0]["geometry"]["coordinates"], 'red', 3))
        preview = BytesIO()
        image = m.render()
        image.save(preview, optimize=True, quality=100, format="JPEG")

        # save file, geojson, activityData, preview to storage container
        saveBlob(upload, activityid + "/source.gpx", "application/gpx+xml")
        saveBlob(json.dumps(routejson).encode(), activityid + "/geojson.json", "application/json")
        saveBlob(json.dumps(activitydata).encode(), activityid + "/activitydata.json", "application/json")
        saveBlob(preview.getvalue(), activityid + "/preview.jpg", "image/jpeg")

        # capture optional form information
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
        activityproperties["gps"] = 1

        # capture distance for gear
        if len(gearid) > 0:
            incrementDecrement("gear", auth["userid"], gearid, "distance", activityproperties["distance"], False)

        # save statistics to tblsvc
        upsertEntity("activities", activityproperties)
        
        return createJsonHttpResponse(201, "successfully uploaded activity", {"activityid": activityid})

    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="upload/media/{activityid}", methods=[func.HttpMethod.POST])
def uploadmedia(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called uploadmedia')
    try:
        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})
        activityid = req.route_params.get("activityid")
        if len(queryEntities("activities", "PartitionKey eq '" + auth['userid'] + "' and RowKey eq '" + activityid + "'")) == 0:
            return createJsonHttpResponse(403, "must be owner of activity to upload media")
        if "upload" not in req.files.keys():
            return createJsonHttpResponse(400, "missing upload file")
        mediaid = str(uuid.uuid4())
        try:
            upload = req.files["upload"].stream.read()
            preview = resizeImage(BytesIO(upload), (300, 300), 80)
            full = resizeImage(BytesIO(upload), (1200, 1200), 95)
            saveBlob(upload, req.route_params.get("activityid") + "/media/" + mediaid + "_original", req.files["upload"].content_type)
            saveBlob(preview, req.route_params.get("activityid") + "/media/" + mediaid + "_preview", "image/jpeg")
            saveBlob(full, req.route_params.get("activityid") + "/media/" + mediaid + "_full", "image/jpeg")
            qe = queryEntities("media", "PartitionKey eq '" + activityid + "'")
            sort = 0
            if len(qe) > 0:
                for e in qe:
                    if e["sort"] > sort:
                        sort = e["sort"]
            upsertEntity("media",{
                "PartitionKey": activityid,
                "RowKey": mediaid,
                "filename": req.files["upload"].filename,
                "sort": sort + 1
            })
            return createJsonHttpResponse(201, "successfully uploaded media", {"mediaid": mediaid})
        except:
            return createJsonHttpResponse(400, "media unsuccesful due to bad data or misunderstood format")
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="activities/{userid?}/{activityid?}", methods=[func.HttpMethod.GET])
def activities(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called activities')

    try:

        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})

        feedresponse = True
        filter = ""

        if "activityid" in req.route_params.keys() and "userid" not in req.route_params.keys():
            return createJsonHttpResponse(400, "activityid must be accompanied by a userid")
        elif "activityid" in req.route_params.keys() and "userid" in req.route_params.keys():
            feedresponse = False
            filter +=  "PartitionKey eq '" + req.route_params.get("userid") + "'" + " and RowKey eq '" + req.route_params.get("activityid") + "'"
        else:
            delta = 86400*7
            endtime = 0
            starttime = 0
            if "endtime" in req.params.keys() and "starttime" in req.params.keys():
                endtime = int(req.params.get("endtime"))
                starttime = int(req.params.get("starttime"))
                if (endtime - starttime > delta):
                    raise Exception("maximum time delta of " + str(delta) + " for activities")
            else:
                endtime = int(time.time())
                starttime = int(endtime - delta)
            filter += "Timestamp le datetime'" + tsUnixToIso(endtime) + "' and Timestamp ge datetime'" + tsUnixToIso(starttime) + "'"
            if "userid" in req.route_params.keys():
                filter += " and PartitionKey eq '" + req.route_params.get("userid") + "'"

        activities = queryEntities("activities", 
            filter,
            aliases={"PartitionKey": "userid", "RowKey": "activityid"},
            sortproperty="starttime", 
            sortreverse=True,
            userid=auth["userid"],
            connectionproperty="PartitionKey")

        userdata = {}
        activitytypes = {}

        for e in queryEntities("validate", "PartitionKey eq 'activitytype'"):
            activitytypes[e.get("RowKey")] = e.get("label")
        
        for a in activities:

            if a.get("gps",1) == 1:
                gps = True
            else:
                gps = False

            if gps:
                a["previewurl"] = "data/preview/" + a["activityid"]

            # normalize
            if a["userid"] not in userdata.keys():
                qu = queryEntities("users","PartitionKey eq '" + a["userid"] + "' and RowKey eq 'account'")
                userdata[a["userid"]] = {"firstname": qu[0]["firstname"], "lastname": qu[0]["lastname"]}
            if len(userdata) > 0:
                a["firstname"] = userdata[a["userid"]]["firstname"]
                a["lastname"] = userdata[a["userid"]]["lastname"]

            # media
            qe = queryEntities("media", "PartitionKey eq '" + a["activityid"] + "'", ["RowKey", "sort"], {"RowKey": "mediaid"}, "sort")
            for e in qe:
                e["mediapreviewurl"] = "data/mediapreview/" + a["activityid"] + "/" + e["mediaid"]
                e["mediafullurl"] = "data/mediafull/" + a["activityid"] + "/" + e["mediaid"]
            a["media"] = qe

            # props
            qe = queryEntities("props", "PartitionKey eq '" + a["activityid"] + "'", ["RowKey","createtime"], {"RowKey": "userid"}, "createtime", True)
            for e in qe:
                e["createtime"] = launderTimezone(e["createtime"], auth["timezone"])
            a["props"] = qe

            # comments
            qe = queryEntities("comments", "PartitionKey eq '" + a["activityid"] + "'", ["RowKey","userid","createtime","comment"], {"RowKey": "commentid"}, "createtime", True)
            for e in qe:
                e["createtime"] = launderTimezone(e["createtime"], auth["timezone"])
            a["comments"] = qe

            # launder
            activitytype = a["activitytype"]
            a_distance = a.get("distance",0)
            a_time = a.get("time",0)
            a_ascent = a.get("ascent",0)
            a_descent = a.get("descent",0)
            a["activitytype"] = activitytypes[a["activitytype"]]
            a["time"] = launderUnits(auth["unitsystem"], "time", in_time=a_time)
            a["distance"] = launderUnits(auth["unitsystem"], "distance", in_distance=a_distance)
            a["ascent"] = launderUnits(auth["unitsystem"], "ascent", in_distance=a_ascent)
            a["descent"] = launderUnits(auth["unitsystem"], "ascent", in_distance=a_descent)
            if activitytype == "run":
                a["speed"] = launderUnits(auth["unitsystem"], "pace", in_distance=a_distance, in_time=a_time)
            else:
                a["speed"] = launderUnits(auth["unitsystem"], "speed", in_distance=a_distance, in_time=a_time)
            a["timestamp"] = launderTimezone(a["timestamp"], auth["timezone"])
            a["starttime"] = launderTimezone(a["starttime"], auth["timezone"])
            
            # add gear, include track path for single activity response
            if not feedresponse:
                if a.get("gearid", None) != None:
                    a["gear"] = queryEntities("gear", "PartitionKey eq '" + a["userid"] + "' and RowKey eq '" + a["gearid"] + "'", ["RowKey","distance","name"], {"RowKey": "gearid"})[0]
                    a["gear"]["distance"] = launderUnits(auth["unitsystem"], "distance", in_distance=a["gear"]["distance"])
                a["trackurl"] = "data/geojson/" + a["activityid"]

            # exclude certain properties and customize response based on type
            excludeproperties = ["timestamp","gearid"]
            if a_distance == 0:
                excludeproperties += ["distance","speed"]
            if a_ascent == 0:
                excludeproperties.append("ascent")
            if a_descent == 0:
                excludeproperties.append("descent")
            for ep in excludeproperties:
                if ep in a.keys():
                    a.pop(ep, None)
            
        response = {"activities": activities}
        if feedresponse:
            nexturl = "activities"
            if "userid" in req.route_params.keys():
                nexturl += "/" + req.route_params.get("userid")
            nexturl += "?endtime=" + str(starttime) + "&starttime=" + str(starttime - delta)
            response["nexturl"] = nexturl

        return func.HttpResponse(json.dumps(response), status_code=200, mimetype="application/json")

    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))
    
@app.route(route="data/{datatype}/{id}/{id2?}", methods=[func.HttpMethod.GET])
def data(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called data')
    try:
        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})
        datatype = req.route_params.get("datatype")
        if not validateData("datatype", datatype)["status"]:
            return createJsonHttpResponse(400, "invalid datatype")
        match datatype:
            case "preview":
                gb = getBlob(req.route_params.get("id") + "/preview.jpg")
                if not gb["status"]:
                    gb = getBlob(req.route_params.get("id") + "/preview.png")
            case "geojson":
                gb = getBlob(req.route_params.get("id") + "/geojson.json")
            case "mediapreview":
                gb = getBlob(req.route_params.get("id") + "/media/" + req.route_params.get("id2") + "_preview")
            case "mediafull":
                gb = getBlob(req.route_params.get("id") + "/media/" + req.route_params.get("id2") + "_full")
            case _:
                return createJsonHttpResponse(400, "invalid datatype")
        if not gb["status"]:
            return createJsonHttpResponse(404, "data not found")
        return func.HttpResponse(gb["data"], status_code=200, mimetype=gb["contenttype"])
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="validate/{validationtype}", methods=[func.HttpMethod.GET])
def validate(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called validate')
    try:
        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})
        if not validateData("validationtype", req.route_params.get("validationtype"))["status"]:
            return createJsonHttpResponse(400, "invalid validationtype")
        data = queryEntities("validate", "PartitionKey eq '" + req.route_params.get("validationtype") + "'",["RowKey","label","sort"],{"RowKey": req.route_params["validationtype"]}, "sort")
        return func.HttpResponse(json.dumps({"validations":data}), status_code=200, mimetype="application/json")
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="login", methods=[func.HttpMethod.GET])
def login(req: func.HttpRequest) -> func.HttpResponse:

    logging.info('called login')

    try:
        
        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})

        return func.HttpResponse('<html><head><title>Outsidely Login</title></head><body><h1><a href="'+str(req.params.get("redirecturl") or "#")+'">Click here to go back</a></h1></body></html>', status_code=200, mimetype="text/html")
    
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="create/{type}/{id?}/{id2?}", methods=[func.HttpMethod.POST])
def create(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called create')
    try:
        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})
        try:
            body = req.get_json()
        except:
            if req.route_params.get("type") != "prop":
                return createJsonHttpResponse(400, "bad json data")
        id = {}
        match req.route_params.get("type"):
            case "activity":
                cjp = checkJsonProperties(body, [{"name":"activitytype","required":True, "validate": True},{"name":"ascent"},{"name":"distance"},{"name":"starttime","required":True},{"name":"time","required":True},{"name":"description"},{"name":"name"},{"name":"gearid"}])
                if not cjp["status"]:
                    return createJsonHttpResponse(400, cjp["message"])
                if len(body.get("gearid",""))>0:
                    if len(queryEntities("gear", "PartitionKey eq '" + auth['userid'] + "' and name eq '" + body["gearid"] + "'")) == 0:
                        return createJsonHttpResponse(400, "gearid not found")
                activityid = str(uuid.uuid4())
                body["PartitionKey"] = auth["userid"]
                body["RowKey"] = activityid
                body["gps"] = 0
                body["starttime"] = parser.isoparse(body["starttime"])
                upsertEntity("activities", body)
                id["activityid"] = activityid
                # capture distance for gear
                if len(body.get("gearid","")) > 0:
                    incrementDecrement("gear", auth["userid"], body["gearid"], "distance", body.get("distance", 0), False)
            case "gear":
                cjp = checkJsonProperties(body, [{"name":"activitytype","required":True,"validate":True},{"name":"name","required":True}])
                if not cjp["status"]:
                    return createJsonHttpResponse(400, cjp["message"])
                if len(queryEntities("gear", "PartitionKey eq '" + auth['userid'] + "' and name eq '" + body["name"] + "'")) > 0:
                    return createJsonHttpResponse(400, "gear with that name already exists")
                gearid = str(uuid.uuid4())
                body["PartitionKey"] = auth["userid"]
                body["RowKey"] = gearid
                body["distance"] = float(0)
                body["retired"] = str("0")
                upsertEntity("gear", body)
                id["gearid"] = gearid
            case "connection":
                cjp = checkJsonProperties(body, [{"name":"connectiontype","required":True,"validate":True},{"name":"userid","required":True}])
                if not cjp["status"]:
                    return createJsonHttpResponse(400, cjp["message"])
                if not useridExists(body["userid"]):
                    return createJsonHttpResponse(404, "userid not found")
                
                # if this connection is already connected then do nothing
                qe = queryEntities("connections", "PartitionKey eq '" + auth["userid"] + "' and RowKey eq '" + body["userid"] + "'")
                if (len(qe)>0):
                    if qe[0].get("connectiontype", "")  == "connected":
                        return createJsonHttpResponse(400, "already connected")

                # if this is a rejection, then remove the records
                if body["connectiontype"] == "rejected":
                    deleteEntity("connections", auth["userid"], body["userid"])
                    deleteEntity("connections", body["userid"], auth["userid"])
                    return createJsonHttpResponse(200, "connection rejected")
                
                # submitting user is confirmed by action
                upsertEntity("connections", {
                    "PartitionKey": auth["userid"],
                    "RowKey": body["userid"],
                    "connectiontype": "confirmed"
                })
                # if this is the creation of the connection pair, add the other user as pending
                qe = queryEntities("connections", "PartitionKey eq '" + body["userid"] + "' and RowKey eq '" + auth["userid"] + "'")
                if len(qe) == 0:
                    upsertEntity("connections", {
                        "PartitionKey": body["userid"],
                        "RowKey": auth["userid"],
                        "connectiontype": "pending"
                    })

                # if both users are confirmed, set to connected
                if len(queryEntities("connections", "(PartitionKey eq '" + auth["userid"] + "' and RowKey eq '" + body["userid"] + "' and connectiontype eq 'confirmed') or (PartitionKey eq '" + body["userid"] + "' and RowKey eq '" + auth["userid"] + "' and connectiontype eq 'confirmed')")) == 2:
                    upsertEntity("connections", {
                        "PartitionKey": auth["userid"],
                        "RowKey": body["userid"],
                        "connectiontype": "connected"
                    })
                    upsertEntity("connections", {
                        "PartitionKey": body["userid"],
                        "RowKey": auth["userid"],
                        "connectiontype": "connected"
                    })
                    incrementDecrement("users", auth["userid"], 'account', "connections", 1, True)
                    incrementDecrement("users", body["userid"], 'account', "connections", 1, True)
            case "prop":
                if req.route_params.get("id") == auth["userid"]:
                    return createJsonHttpResponse(400, "cannot prop self")
                if len(queryEntities("activities", "PartitionKey eq '" + req.route_params.get("id") + "' and RowKey eq '" + req.route_params.get("id2") + "'", userid=auth["userid"], connectionproperty="PartitionKey")) == 0:
                    return createJsonHttpResponse(404, "userid and or activity not found")
                if len(queryEntities("props", "PartitionKey eq '" + req.route_params.get("id2") + "' and RowKey eq '" + auth["userid"] + "'")) > 0:
                    return createJsonHttpResponse(400, "prop already exists")
                upsertEntity("props", {
                    "PartitionKey": req.route_params.get("id2"),
                    "RowKey": auth["userid"],
                    "createtime": tsUnixToIso(time.time())
                })
            case "comment":
                cjp = checkJsonProperties(body, [{"name":"comment","required":True}])
                if not cjp["status"]:
                    return createJsonHttpResponse(400, cjp["message"])
                qe = queryEntities("activities", "PartitionKey eq '" + req.route_params.get("id") + "' and RowKey eq '" + req.route_params.get("id2") + "'", userid=auth["userid"], connectionproperty="PartitionKey")
                if len(qe) == 0:
                    return createJsonHttpResponse(400, "userid and activityid mismatch, or no connection found")
                commentid = str(uuid.uuid4())
                upsertEntity("comments", {
                    "PartitionKey": req.route_params.get("id2"),
                    "RowKey": commentid,
                    "userid": auth["userid"],
                    "comment": body["comment"],
                    "createtime": tsUnixToIso(time.time())
                })
                id["commentid"] = commentid
            case _:
                return createJsonHttpResponse(404, "invalid resource type")
        return createJsonHttpResponse(201, "create successful", id)
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="read/{type}/{id?}", methods=[func.HttpMethod.GET])
def read(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called read')
    try:
        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})
        match req.route_params.get("type"):
            case "user":
                userid = req.route_params.get("id", "")
                if len(userid) == 0:
                    userid = auth["userid"]
                if not useridExists(userid):
                    return createJsonHttpResponse(404, "userid not found")
                properties = ["PartitionKey","firstname", "lastname", "connections", "createtime"]
                if auth["userid"] == userid:
                    for p in ["unitsystem","timezone","email"]:
                        properties.append(p)
                qe = queryEntities("users", 
                                   "PartitionKey eq '" + userid + "' and RowKey eq 'account'", 
                                   properties,
                                   {"PartitionKey": "userid"})
                return func.HttpResponse(json.dumps(qe[0]), status_code=200, mimetype="application/json")
            case "gear":
                gearfilter = ""
                if req.route_params.get("id", None) != None:
                    gearfilter += " and RowKey eq '" + req.route_params.get("id") + "'"
                qe = queryEntities("gear","PartitionKey eq '" + auth["userid"] + "'" + gearfilter, aliases={"PartitionKey":"userid","RowKey":"gearid"}, sortproperty="timestamp", sortreverse=True)
                for e in qe:
                    e["activitytype"] = validateData("activitytype", e["activitytype"]).get("label")
                    e["distance"] = launderUnits(auth["unitsystem"], "distance", in_distance=e["distance"])
                return func.HttpResponse(json.dumps({"gear":qe}), status_code=200, mimetype="application/json")
            case "connections":
                userid = req.route_params.get("id", "")
                if len(userid) == 0:
                    userid = auth["userid"]
                if not useridExists(userid):
                    return createJsonHttpResponse(404, "userid not found")
                filter = ""
                if auth["userid"] != userid:
                    userid = req.route_params["id"]
                    filter = " and connectiontype eq 'confirmed'"
                qe = queryEntities("connections", "PartitionKey eq '" + userid + "'" + filter, ["RowKey", "connectiontype"], {"RowKey": "userid"})
                return func.HttpResponse(json.dumps({"connections":qe}), status_code=200, mimetype="application/json")
            case _:
                return createJsonHttpResponse(404, "invalid resource type")
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="update/{type}/{id}/{id2?}", methods=[func.HttpMethod.PATCH])
def update(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called update')
    try:
        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})
        body = req.get_json()
        match req.route_params.get("type"):
            case "user":
                if len(queryEntities("users", "PartitionKey eq '" + auth['userid'] + "' and RowKey eq 'account'")) == 0:
                    return createJsonHttpResponse(404, "resource not found")
                cjp = checkJsonProperties(body, [{"name":"firstname"},{"name":"lastname"},{"name":"unitsystem"},{"name":"password"}])
                if not cjp["status"]:
                    return createJsonHttpResponse(400, cjp["message"])
                body["PartitionKey"] = auth["userid"]
                body["RowKey"] = "account"
                if "password" in body.keys():
                    if len(body["password"]) < 16:
                        return createJsonHttpResponse(400, "passwords must be at least 16 characters long")
                    salt = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
                    body["password"] = hashlib.sha512(str(salt + body["password"]).encode()).hexdigest()
                    body["salt"] = salt
                upsertEntity("users", body)
            case "activity":
                if len(queryEntities("activities", "PartitionKey eq '" + auth['userid'] + "' and RowKey eq '" + req.route_params.get("id") + "'")) == 0:
                    return createJsonHttpResponse(404, "resource not found")
                cjp = checkJsonProperties(body, [{"name":"activitytype","validate":True},{"name":"name"},{"name":"description"}])
                if not cjp["status"]:
                    return createJsonHttpResponse(400, cjp["message"])
                body["PartitionKey"] = auth["userid"]
                body["RowKey"] = req.route_params.get("id")
                upsertEntity("activities", body)
            case "gear":
                if len(queryEntities("gear", "PartitionKey eq '" + auth['userid'] + "' and RowKey eq '" + req.route_params.get("id") + "' and retired eq 0")) == 0:
                    return createJsonHttpResponse(404, "resource not found")
                cjp = checkJsonProperties(body, [{"name":"activitytype","validate":True},{"name":"name"},{"name":"retired","validate":True}])
                if not cjp["status"]:
                    return createJsonHttpResponse(400, cjp["message"])
                body["PartitionKey"] = auth["userid"]
                body["RowKey"] = req.route_params.get("id")
                upsertEntity("gear", body)
            case "media":
                if len(queryEntities("activities", "PartitionKey eq '" + auth["userid"] + "' and RowKey eq '" + req.route_params.get("id") + "'")) == 0:
                    return createJsonHttpResponse(404, "resource not found")
                if len(queryEntities("activities", "PartitionKey eq '" + auth["userid"] + "' and RowKey eq '" + req.route_params.get("id") + "'")) == 0:
                    return createJsonHttpResponse(403, "must be the activity owner to update media")
                qe = queryEntities("media", "PartitionKey eq '" + req.route_params.get("id") + "' and RowKey eq '" + req.route_params.get("id2") + "'")
                if len(qe) == 0:
                    return createJsonHttpResponse(404, "resource not found")
                cjp = checkJsonProperties(body, [{"name":"sort"}])
                if not cjp["status"]:
                    return createJsonHttpResponse(400, cjp["message"])
                oldsort = qe[0].get("sort")
                qe = queryEntities("media", "PartitionKey eq '" + req.route_params.get("id") + "' and RowKey ne '" + req.route_params.get("id2") + "'", aliases={"PartitionKey":"activityid","RowKey":"mediaid"})
                for e in qe:
                    if "sort" in body.keys():
                        if e["sort"] == body["sort"]:
                            upsertEntity("media", {
                                "PartitionKey": e["activityid"],
                                "RowKey": e["mediaid"],
                                "sort": oldsort
                            })
                body["PartitionKey"] = req.route_params.get("id")
                body["RowKey"] = req.route_params.get("id2")
                upsertEntity("media", body)
            case _:
                return createJsonHttpResponse(404, "invalid resource type")
        return createJsonHttpResponse(200, "update successful")
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))

@app.route(route="delete/{type}/{id}/{id2?}", methods=[func.HttpMethod.DELETE])
def delete(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('called delete')
    try:
        auth = authorizer(req)
        if not auth["authorized"]:
            return createJsonHttpResponse(401, "unauthorized", headers={'WWW-Authenticate':'Basic realm="outsidely"'})
        match req.route_params.get("type"):
            case "user":
                if auth["userid"] != req.route_params.get("id"):
                    return createJsonHttpResponse(403, "accounts can only be deleted by themselves")
                deleteid = queryEntities("users", "PartitionKey eq '" + auth["userid"] + "' and RowKey eq 'account'")[0]["salt"]
                if req.route_params.get("id2", "") == deleteid:
                    activityids = queryEntities("activities", "PartitionKey eq '" + auth["userid"] + "'", ["PartitionKey","RowKey"], {"PartitionKey":"userid","RowKey": "activityid"})
                    # blobs
                    for e in activityids:
                        for b in listBlobs(e["activityid"]):
                            deleteBlob(b)
                    # props - does not delete props made by user on other activities
                    for e in activityids:
                        for e1 in queryEntities("props", "PartitionKey eq '" + e["activityid"] + "'", ["PartitionKey","RowKey"], {"PartitionKey": "activityid", "RowKey": "userid"}):
                            deleteEntity("props", e1["activityid"], e1["userid"])
                    # comments - does not delete comments made by user on other activities
                    for e in activityids:
                        for e1 in queryEntities("comments", "PartitionKey eq '" + e["activityid"] + "'", ["PartitionKey","RowKey"], {"PartitionKey": "activityid", "RowKey": "commentid"}):
                            deleteEntity("comments", e1["activityid"], e1["commentid"])
                    # media
                    for e in activityids:
                        for e1 in queryEntities("media", "PartitionKey eq '" + e["activityid"] + "'", ["PartitionKey","RowKey"], {"PartitionKey": "activityid", "RowKey": "mediaid"}):
                            deleteEntity("media", e1["activityid"], e1["mediaid"])
                    # activities
                    for e in activityids:
                        deleteEntity("activities", e["userid"], e["activityid"])
                    # connections
                    for e in queryEntities("connections", "PartitionKey eq '" + auth["userid"] + "'"):
                        deleteEntity("connections", e["PartitionKey"], e["RowKey"])
                        deleteEntity("connections", e["RowKey"], e["PartitionKey"])
                    # gear
                    for e in queryEntities("gear", "PartitionKey eq '" + auth["userid"] + "'"):
                        deleteEntity("gear", e["PartitionKey"], e["RowKey"])
                    # deletions
                    for e in queryEntities("deletions", "PartitionKey eq '" + auth["userid"] + "'"):
                        deleteEntity("deletions", e["PartitionKey"], e["RowKey"])
                    # user
                    deleteEntity("users", auth["userid"])
                else:
                    return createJsonHttpResponse(200, "to delete account, call delete/user/{deleteid}", {"deleteid": deleteid})
            case "activity":
                qe = queryEntities("activities", "PartitionKey eq '" + auth['userid'] + "' and RowKey eq '" + req.route_params.get("id") +  "'")
                if len(qe) != 1:
                    return createJsonHttpResponse(404, "resource not found")
                # validate gearid
                if "gearid" in qe[0].keys():
                    incrementDecrement("gear", auth["userid"], qe[0]["gearid"], "distance", -1 * qe[0]["distance"], False)
                upsertEntity("deletions", {
                    "PartitionKey": auth["userid"],
                    "RowKey": "activityid",
                    "id": req.route_params.get("id")
                })
                deleteEntity("activities", auth["userid"], req.route_params.get("id"))
            case "media":
                if len(queryEntities("media", "PartitionKey eq '" + req.route_params.get("id") + "' and RowKey eq '" + req.route_params.get("id2") + "'")) != 1:
                    return createJsonHttpResponse(404, "resource not found")
                if len(queryEntities("activities", "PartitionKey eq '" + auth["userid"] + "' and RowKey eq '" + req.route_params.get("id") + "'")) == 0:
                    return createJsonHttpResponse(403, "must be the activity owner to delete media")
                upsertEntity("deletions", {
                    "PartitionKey": auth["userid"],
                    "RowKey": "mediaid",
                    "id": req.route_params.get("id"),
                    "id2": req.route_params.get("id2")
                })
                deleteEntity("media", req.route_params.get("id"), req.route_params.get("id2"))
            case "connection":
                if len(queryEntities("connections", "PartitionKey eq '" + auth["userid"] + "' and RowKey eq '" + req.route_params.get("id") + "'")) != 1:
                    return createJsonHttpResponse(404, "resource not found")
                upsertEntity("deletions", {
                    "PartitionKey": auth["userid"],
                    "RowKey": "userid",
                    "id": req.route_params.get("id")
                })
                deleteEntity("connections", auth["userid"], req.route_params.get("id"))
                deleteEntity("connections", req.route_params.get("id"), auth["userid"])
                incrementDecrement("users", auth["userid"], "account", "connections", -1, True)
                incrementDecrement("users", req.route_params.get("id"), "account", "connections", -1, True)
            case "prop":
                if len(queryEntities("props", "PartitionKey eq '" + req.route_params.get("id2") + "' and RowKey eq '" + auth["userid"] + "'")) == 0:
                    return createJsonHttpResponse(400, "cannot delete prop")
                upsertEntity("deletions", {
                    "PartitionKey": auth["userid"],
                    "RowKey": "prop",
                    "id": req.route_params.get("id")
                })
                deleteEntity("props", req.route_params.get("id"), auth["userid"])
            case "comment":
                # allow deleting a comment if its the owner of the activity
                cnt = 0
                cnt += len(queryEntities("comments", "PartitionKey eq '" + req.route_params.get("id") + "' and RowKey eq '" + req.route_params.get("id2") + "' and userid eq '" + auth["userid"] + "'"))
                if cnt == 0:
                    cnt += len(queryEntities("activities", "PartitionKey eq '" + auth["userid"] + "' and RowKey eq '" + req.route_params.get("id") + "'"))
                if cnt == 0:
                    return createJsonHttpResponse(400, "cannot delete comment")
                upsertEntity("deletions", {
                    "PartitionKey": auth["userid"],
                    "RowKey": "comment",
                    "id": req.route_params.get("id"),
                    "id2": req.route_params.get("id2")
                })
                deleteEntity("comments", req.route_params.get("id"), req.route_params.get("id2"))
            case _:
                return createJsonHttpResponse(404, "invalid resource type")
        return createJsonHttpResponse(200, "delete successful")
    except Exception as ex:
        return createJsonHttpResponse(500, str(ex))