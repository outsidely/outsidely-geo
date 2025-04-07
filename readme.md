# outsidely-geo

GIS, data analysis, and APIs for the outsidely project. Utilizes Azure Functions, Azure Table Service, and Azure Blob Storage.

## APIs

### POST /upload/activity
- Upload a GPX of an activity using multi part form data
- Required: upload (GPX as binary file), activitytype
- Optional: name, description, private (0=default/1)

Response 
```json
{
    "statuscode": 201,
    "message": "successfully uploaded activity",
    "activityid": "faa0c893-7c44-45ae-b618-eab5d03337ad"
}
```

### POST /upload/media/{activityid}
- Can upload images to an activity using multi part form data with the `upload` value being an image file

Response 
```json
{
    "statuscode": 201,
    "message": "successfully uploaded media",
    "mediaid": "37bb5bd8-4312-4a39-bce6-d8a9fec6e833"
}
```

### POST /newuser/{userid}/{invitationid}
- Fulfills an invitation and new user creation request
- The `recoveryid` is very important as it represents the _only_ way to recover an account if the password is forgotten, see `recover` API.

Request
```json
{
    "userid": "unique userid that doesnt already exist in the system",
    "email": "email",
    "firstname": "firstname",
    "lastname": "lastname",
    "password": "password"
}
```

Response 
```json
{
    "statuscode": 201,
    "message": "create successful",
    "recoveryid": "<recoveryid>"
}
```

### POST /recover/{userid}/{recoveryid}
- Allows a user to reset their password if forgotten using a saved recoveryid
- Returns a new recoveryid to be securely saved somewhere

Request 
```json
{
    "password": "<new password>"
}
```

Response 
```json
{
    "statuscode": 200,
    "message": "recovery succesful",
    "recoveryid": "<recoveryid>"
}
```

### GET /activities/{userid?}/{activityid?}
- `/activities` will start at the current time and provide a feed of all activities as well as a continuation url to follow for more
- `/activities/{userid}` will create a feed limited to the provided userid
- `/activities/{userid}/{activityid}` will filter to just one activity
    - Also includes gear info and trackurl

### GET /data/{datatype}/{id}/{id2?}
- Gets binary data objects stored in blob storage
- `datatype` is a valid value from `/validate/datatype`
- `id` is the id of the data to retrieve
- `id2` is optional for pulling nested data in some cases
- `/data/preview/{activityid}` gets a preview for an activityid
- `/data/geojson/{activityid}` gets a geojson for an activityid
- `/data/activity/{activityid}` gets the raw activity data for an activityid
- `/data/mediapreview/{activityid}/{mediaid}` gets a preview size media object
- `/data/mediafull/{activityid}/{mediaid}` gets a full size media object

### GET /validate/{validationtype}
- Built as a generic way to have constrained system values.
- Current validations available at `/validate/validationtype`

### Other CRUD

These all share similar code and routines with customization for some cases (changing password, for example). These will provide access for users, activities, gear, comments, media, and props.

### POST /create/gear
Request
```json
{
    "activitytype": "a valid value from /validate/activitytype",
    "name": "name of the piece of gear"
}
```
Response
```json
{
    "statuscode": 201,
    "message": "create successful",
    "gearid": "<gearid>"
}
```

### POST /create/connection
To create a connection, one user must initiate. This is done using connectiontype of "confirmed". The other userid will then be listed as "pending" unless they also "confirm" or they choose to "reject".
Request
```json
{
    "connectiontype": "a valid value from /validate/connectiontype",
    "userid": "userid of the person to attempt to connect to"
}
```

### POST /create/prop/{userid}/{activityid}
No body is required to give props.

### POST /create/comment/{userid}/{activityid}
Request
```json
{
    "comment": "the comment text"
}
```

### POST /create/activity
Create a manual activity without a GPS file.

Request
```json
{
    "activitytype": "valide activitytype from validate/activitytypes",
    "ascent": 123.4,
    "descent": 123.4,
    "starttime": "iso 8601 string",
    "time": 312342,
    "description": "string",
    "name": "name",
    "gearid": "valid gearid",
    "private": "0 or 1"
}
```

### GET /read/gear
Response
```json
{
    "gear":[
        {
            "createtime": "2025-03-01T15:50:20.346135+00:00",
            "activitytype": "ride",
            "distance": "laundered",
            "name": "GT Sensor",
            "userid": "jamund",
            "gearid": "088072ad-63b8-4a9b-846a-64ae793cf9e5",
            "retired": 1
        },
        {
            "createtime": "2025-03-01T15:23:46.261960+00:00",
            "activitytype": "ride",
            "distance": "laundered",
            "name": "Transition Sentinel",
            "userid": "jamund",
            "gearid": "7d739518-23da-411b-8e35-3b4173ab94bc",
            "retired": 0
        }
    ]
}
```

### GET /read/connections
Acceptable values and normalization for connectiontype are available in `/validate/connectiontype`

Response
```json
{
    "connections":[
        {
            // you and mamund are connected
            "userid":"mamund",
            "connectiontype":"connected"
        },
        {
            // you have received a connection request from userid="damund" and have yet to respond with connectiontype of "confirmed" or "rejected"
            "userid":"damund",
            "connectiontype":"pending"
        },
        {
            // this means that the calling user sent a request and it that lamund has a "pending" connectiontype
            "userid":"lamund",
            "connectiontype":"confirmed"
        }
    ]
}
```

### GET /read/user/{userid?}
If no userid is provided, the information returned is for the calling user. Certain fields only return for a calling user.

Response
```json
{
    "connections": 0, 
    "createtime": "2025-03-09T01:06:34.428317+00:00", 
    "userid": "jamund",
    "firstname": "Jesse", 
    "lastname": "Amundsen",
    // next three only return for calling user
    "timezone": "America/New_York", 
    "unitsystem": "imperial",
    "email": "fake@email.com"
}
```

### GET /read/notifications
Response
```json
{
    "notifications": [
        {
            "createtime": "2025-04-06T23:37:20Z",
            "message": "Welcome to Outsidely!",
            "options": [
                {
                    "text": "Clear",
                    "url": "delete/notification/40465142-e525-4329-955d-c13b634e2c22",
                    "method": "DELETE",
                    "body": null
                }
            ],
            "notificationid": "40465142-e525-4329-955d-c13b634e2c22"
        },
        {
            "createtime": "2025-04-06T23:42:23Z",
            "message": "mamund wants to connect with you.",
            "options": [
                {
                    "text": "Connect",
                    "url": "create/connection",
                    "method": "POST",
                    "body": "{\"userid\":\"mamund\",\"connectiontype\":\"confirmed\"}"
                },
                {
                    "text": "Reject",
                    "url": "create/connection",
                    "method": "POST",
                    "body": "{\"userid\":\"mamund\",\"connectiontype\":\"rejected\"}"
                }
            ],
            "notificationid": "aaecf3e4-1c6a-4fd9-a2ec-8b4b5e384987"
        }
    ]
}
```

### PATCH /update/user/{userid}
Request
```json
{
    "firstname": "Joe",
    "lastname": "Smith",
    "unitsystem": "a valid value from /validate/unitsystem",
    "password": "at least 16 characters long"
}
```

### PATCH /update/activity/{activityid}
Request
```json
{
    "activitytype": "a valid value from /validate/activitytype",
    "name": "name of the activity",
    "description": "description of the activity"
}
```

### PATCH /update/gear/{gearid}
Request
```json
{
    "name": "name of the piece of gear",
    "activitytype": "a valid value from /validate/activitytype",
    "retired": "a valid value from /validate/retired"
}
```

### PATCH /update/media/{activityid}/{mediaid}
Request
- sort is an integer in the range of current sort values for the given activityid, issuing a new sort will _swap_ the sort values
```json
{
    "sort": 3
}
```

### DELETE /delete/activity/{activityid}
Response
```json
{
    "statuscode": 200,
    "message": "delete successful"
}
```

### DELETE /delete/media/{activityid}/{mediaid}
Response
```json
{
    "statuscode": 200,
    "message": "delete successful"
}
```

### DELETE /delete/connection/{userid}
Response
```json
{
    "statuscode": 200,
    "message": "delete successful"
}
```

### DELETE /delete/prop/{activityid}
Response
```json
{
    "statuscode": 200,
    "message": "delete successful"
}
```

### DELETE /delete/comment/{activityid}/{commentid}
Response
```json
{
    "statuscode": 200,
    "message": "delete successful"
}
```

### DELETE /delete/notification/{notificationid}
Response
```json
{
    "statuscode": 200,
    "message": "delete successful"
}
```

### GET /whoami
Returns information about the current user context.

Response
```json
{
    "userid":"jamund"
}
```

## Azure Resources
- Resource Group: outsidely
- Function App: outsidely-app-geo
- Storage Account: outsidelystorage
- Application Insights: outsidely-appinsights

## Processing Data Models

### Activity Data
Objects should be in the array ordered by timestamp.
- **timestamp** - string - required - ISO 8601 formatted, UTC+0
- **longitude** - number - required - WGS84 Longitude
- **latitude** - number - required - WGS84 Latitude
- **elevation** - number - Elevation in meters
```javascript
{
    "version" 1,
    "data": [
        {
            "timestamp": "2019-11-14T00:55:31.820Z",
            "longitude": -84.73334,
            "latitude": 34.9392932,
            "elevation": 382.98
        },
        ...
    ]
}
```

### Statistics Data
- **time** - number - required - Total time elapsed for the activity in seconds
- **distance** - number - required - Total length of the activity in meters
- **ascent** - number - Total ascent of the activity in meters
- **descent** - number - Total descent of the activity in meters
```javascript
{
    "version": 1
    "time": 9786,
    "distance": 14361.84244,
    "ascent": 588.402,
    "descent": 570.111
}
```

## Tables / Storage / CRUD Outline

[Google Doc Link](https://docs.google.com/spreadsheets/d/1w3IJKmRbWVmeEW3whp3uNintAZ6bExaaPi4kNrGqgR8/edit?usp=sharing)

## Work Items
- Finalize activitytype approach (needs discussion, thought)
    - gps: 1, 0
    - assisted: 0, 1
    - activitytype: run, ride, other
        - stats happen at this level unless a subtype is requested?
    - activitysubtype: run, walk, mountain bike, gravel - purely for display
- Bugs or behavioral issues
    - Quirk: whenever the record is touched, the Timestamp changes. So if someone keeps updating their activity it will always jump to the top. Even if it's mega old. Probably want to implement some sort of check about if it's a lot older than the original posting time then filter it out?
    - Issue: consider activityid=710e05fd-61c8-456c-be38-5eb90ad1a045 why is the starttime wrong? device issue? 
    - Activity starttime should probably be localized to where the person performed the activity? or is it just their usual timezone? How does this effect ordering?
- Long term
    - Notifications support
    - Rate limiting for all API calls combined to prevent abuse
    - Weekly, Monthly, Yearly stat capability
    - Moving time
    - Smoothing for elevation
    - Smoothing for activity distance
    - Support using DEM-based elevation
    - Privacy zones
    - Duplicate activity detection
    - Support video posting for media
    - `delete/user` is not really complete. Users can't fully delete themselves because their comments they made on activities not their own are not deleted. There's no way to do so without doing full table scans. Option would be to build a crawling service that just checks every night by long running queries against a list of "find and delete this" in a table.
- Reference
    - useful for smoothing distance https://stackoverflow.com/questions/47068504/where-to-find-python-implementation-of-chaikins-corner-cutting-algorithm
    - useful for smoothing elevation https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.CubicSpline.html#scipy.interpolate.CubicSpline
    - useful for reading fit files https://fitdecode.readthedocs.io/en/latest/