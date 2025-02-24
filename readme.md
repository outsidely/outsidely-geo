# outsidely-geo

GIS, data analysis, and web APIs for the outsidely project. Utilizes Azure Functions, Azure Table Service, and Azure Blob Storage.

## APIs

### POST upload
- Upload a GPX of an activity using multi part form data
- Required: upload (GPX as binary file), userid, password, activitytype
- Optional: name, description
- Successful response `{"statuscode":201,"message": "Successfully created activity","activityid":"faa0c893-7c44-45ae-b618-eab5d03337ad"}`

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

### Statisics Data
- **time** - number - required - Total time elapsed for the activity in seconds
- **distance** - number - required - Total length of the activity in meters
- **ascent** - number - Total ascent of the activity in meters
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
    - Consider renaming secret to password so browsers will autofill it in
    - Create one API that handles retrieving data from blob storage rather than one for each type of request (replaces preview)
    - Activities response returns laundered information
        - activitytype to label
        - converted values based on metric/imperial selection for a current user
        - speed/pace depending on activitytype
- High
    - Agree on authentication scheme - needed for gear, comments, photos, and all user-based preferences
- Medium
    - Gear (create update, delete)
    - Comments (create, delete)
    - Photos (create, delete)
    - Map for the activity page w/ elevation profile and linked event support
- Low
    - System for incorporating more activitytypes as time goes on (ebike, kayak, swimming, pickleball, etc)
    - Like/Seen/Kudos for activities
    - Weekly, Monthly, Yearly stats
- Long term
    - Moving time
    - Smoothing for elevation
    - Support using DEM-based elevation
    - Privacy zones