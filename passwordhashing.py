import secrets
import string
import hashlib

salt = ''
password = 'test'

if len(salt or "") == 0:
    salt = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
hash = hashlib.sha512(str(salt + password).encode()).hexdigest()

print(salt)
print(hash)