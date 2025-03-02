#/bin/bash

if [ $# -eq 0 ]; then
  echo "Usage: ./processGpx.sh <gpxfile> <userid> <password> <activitytype=run,ride,other>"
  exit 1
fi

curl "https://outsidely-geo-app.azurewebsites.net/api/upload/activity" -F upload="@$1" -F userid="$2" -F password="$3" -F activitytype="$4" --output -