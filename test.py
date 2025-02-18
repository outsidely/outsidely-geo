from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
import json
import os
from azure.data.tables import TableServiceClient, TableClient
import datetime

os.environ["storageaccount_connectionstring"] = "DefaultEndpointsProtocol=https;AccountName=outsidelystorage;AccountKey=41GZ5nit1vilCAa+nBxwGy9hvRz5WMsGugWGI2ICv3+XcFpxy/5z03i/AbKr7yvFl5l6mYgLJxJa+AStTw8fOw==;EndpointSuffix=core.windows.net"

PRODUCT_ID = u'001234'
PRODUCT_NAME = u'RedMarker'

my_entity = {
    u'PartitionKey': PRODUCT_NAME,
    u'RowKey': PRODUCT_ID,
    u'Stock': 15,
    u'Price': 9.99,
    u'Comments': u"great product",
    u'OnSale': True,
    u'ReducedPrice': 7.99,
    u'PurchaseDate': datetime.datetime(1973, 10, 4),
    u'BinaryRepresentation': b'product_name'
}

table_service_client = TableServiceClient.from_connection_string(os.environ["storageaccount_connectionstring"])
table_client = table_service_client.get_table_client("activities")
table_client.upsert_entity(my_entity)