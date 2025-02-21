#/bin/bash

if [ $# -eq 0 ]; then
  echo "Usage: ./processGpx.sh <gpxfile> <userid> <activitytype=run,ride,other>"
  exit 1
fi

curl "http://localhost:7071/api/upload" -F upload="@$1" -F userid="$2" -F activitytype="$3" --output -