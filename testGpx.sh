#/bin/bash

#usage: testGpx.sh <gpxfile>

#behavior: uploads the gpx, converts it to geojson in the current dir, creates a static preview map in the current dir

curl "https://outsidestuff-function.azurewebsites.net/api/uploadActivity" -H "Content-Type: application/gpx+xml" -d "@$1" --output "$1.geojson"
curl "https://outsidestuff-function.azurewebsites.net/api/createStaticMap" -H "Content-Type: application/json" -d "@$1.geojson" --output "$1.png"