#!/usr/bin/env python
# -*- coding: utf-8 -*-

import whalesnake as ws

IMAGE = 'ubuntu:latest'
CMD = 'ping -c 10 -q {0}'
containers = []
hosts = [
    'google.com',
    'github.com',
    'python.org',
    'docker.com',
]

for host in hosts:
    ctn = ws.Container('ctn_' + host)
    ctn.run(IMAGE, CMD.format(host))
    containers.append(ctn)

while len(containers) > 0:
    for i, ctn in enumerate(containers):
        ctn._check_status()
        if not ctn.running:
            print('')
            print(ctn.logs())
            print(('-') * 70 + '\n')
            ctn.remove()
            del containers[i]

