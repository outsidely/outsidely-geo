#/bin/bash

if [ $# -eq 0 ]; then
  echo "Usage: ./processGpx.sh <gpxfile> <userid> <password> <activitytype=run,ride,other>"
  exit 1
fi

curl "http://localhost:7071/api/upload/activity" -F upload="@$1" -H "@:C:\Temo\auth_outsidely.txt" -F activitytype="$4" --output -