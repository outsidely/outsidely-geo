# outsidely-geo

GIS and data analysis focused work related to the outsidely project. Utilizes Azure Functions, Azure Table Service, and Azure Blob Storage.

## Standard Data Models

### activityModel
- **timestamp** - string - ISO 8601 formatted, UTC+0
- **longitude** - number - WGS84 Longitude
- **latitude** - number - WGS84 Latitude
- **elevation** - number - Elevation in meters
- **properties** - object -  containing all other non-essential properties
```javascript
[
    {
        "timestamp": "2019-11-14T00:55:31.820Z",
        "longitude": -84,
        "latitude": 34,
        "elevation": 382.98,
        "properties": {
            "additionalParam1": 0,
            "additionalParam2": "value2"
        }
    },
    ...
]
```

### statisticsModel
- **time** - number - Total time elapsed for the activity in seconds
- **distance** - number - Total length of the activity in meters
- **ascent** - number - Total ascent of the activity in meters
```javascript
{
    "time": 9786,
    "distance": 14361.84244,
    "ascent": 588.402
}
```

## Table Service Approach

### Users
- PartitionKey/RowKey is the `userId`
- Properties
    - email
    - First name
    - Last name
    - 

### Activities
- PartitionKey is the `userId`
- RowKey is `activityId`
- Properties
    - Source File
    - Preview Image (png)
    - Activity Type (GPS: Run Bike,Non-GPS: Workout)
    - Timestamp
    - Time (s)
    - Distance (m)
    - Ascent (m)
    - Descent (m)
    - Future
        - Moving Time (s)
        - Average Moving Speed (m/s)

## Blob Storage Approach

### Activities
Path is `activityId`\`fileType`
- `sourceFile` Source file of the activity (gpx)
- `geoJson` GeoJSON file for mapping (geojson)
- `activityModel` Custom activity model

### Photos

