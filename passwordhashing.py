import secrets
import string
import hashlib

length = 16
salt = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))
print(salt)

password = 'wcUvrPZ3TnsK5SKMMmZyyrcWGFSkwfux'

hash = hashlib.sha512(str(salt + password).encode()).hexdigest()

print(hash)