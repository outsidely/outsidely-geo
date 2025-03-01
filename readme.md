# outsidely-geo

GIS, data analysis, and web APIs for the outsidely project. Utilizes Azure Functions, Azure Table Service, and Azure Blob Storage.

## APIs

### POST upload
- Upload a GPX of an activity using multi part form data
- Required: upload (GPX as binary file), userid, password, activitytype
- Optional: name, description
- Successful response `{"statuscode":201,"message": "successfully created activity","activityid":"faa0c893-7c44-45ae-b618-eab5d03337ad"}`

### GET activities
- Get information about activities with lots of customization for the response
- `/activities` will start at the current time and provide a feed of all activities as well as a continuation url to follow for more
- `/activities?userid=jamund` will create a feed limited to the provided userid
- `/activities?userid=jamundsen&activityid=d54ece30-8ced-438d-80f8-674bcd45270b` will filter to just one activity

### GET data
- Gets binary data objects stored in blob storage
- `/data?datatype=preview&activityid=d54ece30-8ced-438d-80f8-674bcd45270b` gets a preview png for an activityid
- `/data?datatype=geojson&activityid=d54ece30-8ced-438d-80f8-674bcd45270b` gets the raw geojson for an activityid for map display

### GET validations
- Built as a generic way to have constrained system values.
- Currently used for activitytypes by calling `/validations?validationtype=activitytypes`
- Example of future usage `/validations?validationtype=unitsystem`

### Other CRUD

These all share similar code and routines with customization for some cases (changing password, for example). These will provide access for users, activities, gear, comments, photos, and props.

### POST /create/gear
Request
```json
{
    "activitytype": "a valid value from /validations?validationtype=activitytype",
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

### GET /read/gear
Response
```json
[
    {
        "timestamp": "2025-03-01T15:50:20.346135+00:00",
        "activitytype": "ride",
        "distance": 0,
        "name": "GT Sensor",
        "time": 0,
        "userid": "jamund",
        "gearid": "088072ad-63b8-4a9b-846a-64ae793cf9e5"
    },
    {
        "timestamp": "2025-03-01T15:23:46.261960+00:00",
        "activitytype": "ride",
        "distance": 0,
        "name": "Transition Sentinel",
        "time": 0,
        "userid": "jamund",
        "gearid": "7d739518-23da-411b-8e35-3b4173ab94bc"
    }
]
```

### PATCH /update/user/{userid}
Request
```json
{
    "firstname": "Joe",
    "lastname": "Smith",
    "unitsystem": "a valid value from /validations?validationtype=unitsystem",
    "password": "at least 16 characters long"
}
```

### PATCH /update/activity/{activityid}
Request
```json
{
    "activitytype": "a valid value from /validations?validationtype=activitytype",
    "name": "name of the activity",
    "description": "description of the activity"
}
```

### PATCH /update/gear/{gearid}
Request
```json
{
    "name": "name of the piece of gear",
    "activitytype": "a valid value from /validations?validationtype=activitytype"
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

### DELETE /delete/gear/{gearid}
Response
```json
{
    "statuscode": 200,
    "message": "delete successful"
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
[
    {
        "timestamp": "2019-11-14T00:55:31.820Z",
        "longitude": -84.73334,
        "latitude": 34.9392932,
        "elevation": 382.98
    },
    ...
]
```

### Statistics Data
- **time** - number - required - Total time elapsed for the activity in seconds
- **distance** - number - required - Total length of the activity in meters
- **ascent** - number - Total ascent of the activity in meters
- **descent** - number - Total descent of the activity in meters
```javascript
{
    "time": 9786,
    "distance": 14361.84244,
    "ascent": 588.402,
    "descent": 570.111
}
```

## Tables

### Users
- PartitionKey `userid`
- RowKey `account`
    - email
    - firstname
    - lastname
    - timezone
    - avatar (blob storage)

### Activities
- PartitionKey `userid`
- RowKey `activityid`
    - name
    - description
    - activitytype (run, ride, other)
    - starttime
    - time
    - distance
    - ascent
    - descent

### Comments
- PartitionKey `activityid`
- RowKey `commentid`
    - `userid`
    - timestamp
    - comment

### Photos
- PartitionKey `activityid`
- RowKey `photoid`
    - Path

## Blob Storage Approach

### Activities
Files stored in path of `activityid`
- `source.gpx` - Source file of the activity
- `geojson.json` - GeoJSON file for mapping (geojson)
- `activityData.json` - Custom activity model (json)

### Photos
Path is `activityid`\photos\\`photoid`

## Work Items
- Unclassified
    - Get outsidely@gmail.com email
- High
    - ~~Agree and implement auth scheme - needed for gear, comments, photos, and all user-based preferences~~
- Medium
    - CRUD outline: https://docs.google.com/spreadsheets/d/1w3IJKmRbWVmeEW3whp3uNintAZ6bExaaPi4kNrGqgR8/edit?usp=sharing 
        - ~~Gear~~, Comments, Photos, Props
    - Activities response returns laundered information
        - activitytype to label
        - converted values based on metric/imperial selection for a current user
        - speed/pace depending on activitytype
    - Map for the activity page w/ elevation profile and linked event support
- Low
    - Look at activities as a sort of hierarchy?
        - gps: 1, 0
        - assisted: 0, 1
        - activitytype: feet, wheels, workout
            - stats happen at this level unless a subtype is requested
        - activitysubtype: run, walk, mountain bike, gravel
    - Weekly, Monthly, Yearly stats
- Long term
    - Moving time
    - Smoothing for elevation
    - Support using DEM-based elevation
    - Privacy zones
    - Duplicate activity detection
    - Users get recovery codes since no email / other way to recover
    - Manual activity entries
    - Users can generate a code and invite new users (one code per new user)
