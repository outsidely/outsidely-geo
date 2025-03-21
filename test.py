from azure.storage.blob import BlobServiceClient, BlobClient, ContentSettings

blobserviceclient = BlobServiceClient.from_connection_string("DefaultEndpointsProtocol=https;AccountName=outsidelystorage;AccountKey=41GZ5nit1vilCAa+nBxwGy9hvRz5WMsGugWGI2ICv3+XcFpxy/5z03i/AbKr7yvFl5l6mYgLJxJa+AStTw8fOw==;EndpointSuffix=core.windows.net")
containerclient = blobserviceclient.get_container_client("outsidelycontainer")
blobs = containerclient.list_blobs("0af27737-6d16-474c-8aea-0c5b953ed7ae")
for b in blobs:
    print(b.name)