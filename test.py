from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
import json
import os
from azure.data.tables import TableServiceClient, TableClient
import datetime

response = [{"date":1,"timestamp":"2025-02-18T02:19:54+0000"}
 ,{"date":4,"timestamp":"2025-02-17T17:02:04+0000"}
 ,{"date":2,"timestamp":"2025-02-18T02:19:37+0000"}]

print(response)

response.sort(key=lambda x: x["timestamp"])

print (response)