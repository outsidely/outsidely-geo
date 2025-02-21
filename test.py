from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
import json
import os
from azure.data.tables import TableServiceClient, TableClient
import datetime
import io

os.environ["storageaccount_connectionstring"] = "DefaultEndpointsProtocol=https;AccountName=outsidelystorage;AccountKey=41GZ5nit1vilCAa+nBxwGy9hvRz5WMsGugWGI2ICv3+XcFpxy/5z03i/AbKr7yvFl5l6mYgLJxJa+AStTw8fOw==;EndpointSuffix=core.windows.net"

def getBlob(name):
    blob_service_client = BlobServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
    blob_client = blob_service_client.get_blob_client("outsidelycontainer", name)
    blob = io.BytesIO()
    blob = blob_client.download_blob().readall()
    return {"blob": blob, "contentType": "image/png"}

blob = getBlob("62ec8405-419c-4470-a1d1-aff46e99eb4c/preview.png")
print("howdy")