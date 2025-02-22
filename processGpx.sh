#/bin/bash

if [ $# -eq 0 ]; then
  echo "Usage: ./processGpx.sh <gpxfile> <userid> <secret> <activitytype=run,ride,other>"
  exit 1
fi

curl "https://outsidely-geo-app.azurewebsites.net/api/upload" -F upload="@$1" -F userid="$2" -F secret="$3" -F activitytype="$4" --output -