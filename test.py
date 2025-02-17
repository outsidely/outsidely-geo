import uuid
import base58

uuidvalue = uuid.uuid4()
print(uuidvalue)

uuidbytes = uuidvalue.bytes
print(uuidbytes)

b58str_encode = base58.b58encode(uuidbytes).decode()
print(b58str_encode)