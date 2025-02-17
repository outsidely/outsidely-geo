# outsidely-geo

## Table Service Approach

**Users**
- PartitionKey/RowKey is the `userId`
- Properties
    - email
    - First name
    - Last name
    - 

**Activities**
- PartitionKey is the `userId`
- RowKey is `activityId`
- Properties
    - Source File
    - Preview Image (png)
    - Activity Type (GPS: Run Bike,Non-GPS: Workout)
    - Timestamp
    - Total Time (s)
    - Moving Time (s)
    - Distance (m)
    - Elevation (m)
    - Average Speed (m/s)
    - Average Moving Speed (m/s)

## Blob Storage Approach

**Activities**
- path is `activityId`\`[geoJson,activityModel]`
    - Source file of the activity (gpx, fit)
    - `geoJson` GeoJSON file for mapping (geojson)
    - `activityModel` Custom activity model

**Photos**
