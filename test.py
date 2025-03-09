connections = ["1","2","3","4","5","6","7","8","9","10","11"]

def splitList(list, size):
    for i in range(0, len(list), size):
        yield list[i:i + size]

for c in splitList(connections,10):
    print(c)