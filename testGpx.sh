#/bin/bash

#usage: testGpx.sh <gpxfile>

#behavior: uploads the gpx, converts it to geojson in the current dir, creates a static preview map in the current dir

curl "https://outsidely-geo-app.azurewebsites.net/api/uploadActivityTest" -H "Content-Type: application/gpx+xml" -d "@$1" --output "$1.geojson"
curl "https://outsidely-geo-app.azurewebsites.net/api/createStaticMap" -H "Content-Type: application/json" -d "@$1.geojson" --output "$1.png"
curl "https://outsidely-geo-app.azurewebsites.net/api/createStatisticsData" -H "Content-Type: application/json" -d "@$1.geojson" --output "$1.json"