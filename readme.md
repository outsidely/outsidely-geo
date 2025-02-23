# outsidely-geo

GIS, data analysis, and web APIs for the outsidely project. Utilizes Azure Functions, Azure Table Service, and Azure Blob Storage.

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
    - 
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
- High
    - Comments
    - Photos
- Medium
    - Gear (create update, delete)
    - Comments (create, delete)
    - Photos (create, delete)
- Low
    - Moving time
    - Smoothing for elevation