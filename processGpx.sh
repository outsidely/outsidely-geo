#/bin/bash

if [ $# -eq 0 ]; then
  echo "Usage: ./processGpx.sh <path to gpx file> <userId> <activityType>"
  exit 1
fi

curl "https://outsidely-geo-app.azurewebsites.net/api/uploadActivity" -F upload="@$1" -F userId="$2" -F activityType="$3" --output -