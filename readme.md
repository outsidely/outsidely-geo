# outsidely-geo

GIS and data analysis focused work related to the outsidely project. Utilizes Azure Functions, Azure Table Service, and Azure Blob Storage.

## Processing Data Models

### activityDataModel
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
- PartitionKey `userId`
- RowKey `account`
- Email
- First name
- Last name
- Time zone
- Avatar

### Activities
- PartitionKey `userId`
- RowKey `activityId`
- Name
- Description
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

### Comments
- PartitionKey `activityId`
- RowKey `commentId`
- `userId`
- Comment

### Photos
- PartitionKey `activityId`
- RowKey `photoId`
- Path

## Blob Storage Approach

### Activities
Path is `activityId`\   `fileType`
- `sourceFile` - Source file of the activity
- `geoJson` - GeoJSON file for mapping (geojson)
- `activityModel` - Custom activity model (json)

### Photos
Path is `activityId`\photos\\`photoId`