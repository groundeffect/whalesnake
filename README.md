whalesnake
==========

whalesnake aims to be an intuitive high-level, object-oriented client to access the docker daemon from Python. The heavy lifting is done by docker-py, which is also the only dependency.

So far tested with Python 2.7 & 3.4, docker API 1.13 & 1.14 and docker-py 0.4.0.

Usage
=====

```python
import whalesnake as ws

# should work fine if you didn't change where the docke daemon listens
ws.connect()

# list containers that have 'redis' in their name
ctns = ws.containers('redis')

# check if there is one
if ctns:
    # pick the first one
    ctn = ctns[0]
    # start if not running
    if not ctn.running:
        ctn.start()
    # get the logs
    print(ctn.logs())

# create one!
else:
    # sets up, but does not yet create a container with the name 'redis_ctn'
    ctn = ws.Container('redis_ctn')
    # pull the official redis image from the docker hub, create and fire up the container
    ctn.run('redis:latest')
    # see what's going on inside the container
    ctn.top()

# clean everything up
redis_img = ctn.image
ctn.stop()
ctn.remove()
redis_img.remove()

```

See also the `examples` folder.

