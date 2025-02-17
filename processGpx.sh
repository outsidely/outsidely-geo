#/bin/bash
curl "https://outsidely-geo-app.azurewebsites.net/api/uploadActivity" -H "Content-Type: application/gpx+xml" -d "@$1" --output "$1.geojson"
curl "https://outsidely-geo-app.azurewebsites.net/api/createStaticMap" -H "Content-Type: application/json" -d "@$1.geojson" --output "$1.png"
curl "https://outsidely-geo-app.azurewebsites.net/api/createStatisticsData" -H "Content-Type: application/json" -d "@$1.geojson" --output "$1.json"