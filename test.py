import json

def createJsonHttpResponse(statusCode, message, properties = {}):
    
    response = {}
    response["statusCode"] = statusCode
    response["message"] = message
    for k,v in properties.items():
        if (k not in ["statusCode", "message"]):
            raise ValueError("Properties cannot be named statusCode or message")
        else:
            response[k] = v
    return json.dumps(response)