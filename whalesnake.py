#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import datetime

try:
    import ujson as json
except ImportError:
    import json

import docker

# try to avoid using six for now
try:
  basestring
except NameError:
  basestring = str

# missing in docker-py:
# 'load', 'pause', 'save', 'unpause'
# (un)pause seems rather easy to implement. see:
# https://docs.docker.com/reference/api/docker_remote_api_v1.13/

# also, the following parameters when creating/starting a container:
# "PortSpecs":null, "OnBuild":null, "Cpuset":"0,1"
# as intercepted with:
# sudo strace -e open,read,write -s 4096 -fp docker_daemon_pid_here
# for: docker run -it --rm --cpuset=0,1 ubuntu /bin/bash
# could just be added to _container_config() in client.py!

# additional methods in docker-py (at least not defined here yet):
# 'attach_socket', 'get_image' (seems to return raw image?) , 'resize'

# write a helper, that prints a stream to stdout whenever new data arrives

dc = None

def connect(url='unix://var/run/docker.sock', latest=True, **kwargs):
    '''
    url: Location where the docker daemon listens for requests
    latest: autodetect the servers api version
    
    Possible docker-py arguments and their defaults (in 0.4.0):
    version='1.12', timeout=60, tls=False
    
    '''
    # get rid of that global rather sooner than later
    global dc
    if dc:
        return
    dc = docker.Client(base_url=url, **kwargs)
    if latest and not 'version' in kwargs.keys():
        # reconnect using latest available version
        api_v = dc.version()['ApiVersion']
        #del kwargs['version']
        dc = docker.Client(base_url=url, version=api_v, **kwargs)

def check_docker_id(d_id):
    short_id = None
    long_id = None
    id_len = len(d_id)
    
    try:
        if id_len is 12:
            int(d_id, 16)
            short_id = d_id
        elif id_len is 64:
            int(d_id, 16)
            short_id = d_id[:12]
            long_id = d_id
    except ValueError: # caused by int() conversion
        raise ValueError('ID is not a valid hex-string')  
    
    if not short_id:
        raise ValueError('ID should either be 12 or 64 characters long')
    
    return short_id, long_id

def check_image_name(name):
    ns, repo, tag = None, None, None

    if name.count('/') > 1 or name.count(':') > 1:
        raise ValueError('Only one of each is allowed in an image name: / :')
        
    if '/' in name:
        ns, repo = name.split('/')
        if not ns or not repo:
            raise ValueError('Both, namespace and repo must be supplied.')
        
        if ':' in repo:
            repo, tag = repo.split(':')
            if not tag:
                raise ValueError('Tag must be supplied.')
    
    elif ':' in name:
        repo, tag = name.split(':')
        if not repo or not tag:
            raise ValueError('Both, repo and tag must be supplied.')
    else:
        repo = name
    
    if ns and not re.match(r'^[a-z0-9_]{4,30}$', ns):
        raise ValueError('Namespace did not match [a-z0-9_]{4,30}')
    if not re.match(r'^[a-z0-9-_.]+$', repo):
        raise ValueError('Repo did not match [a-z0-9-_.]+')
    
    return ns, repo, tag

def check_container_name(name):
    '''
    Valid chars, as defined in error msg by docker when trying: 
    c.create_container('busybox:latest', name='test/withslash')
    
    '''
    if not re.match('^[a-zA-Z0-9_.-]+$', name):
        raise ValueError(
            'Only [a-zA-Z0-9_.-] are valid characters for a container name.'
        )

def exists(method):
    def wrap(self, *args, **kwargs):
        if self.exists and not must_exist:
            raise WhalesnakeError(
                'Container was already created, but must not exist.'
            )
        if not self.exists and must_exist:
            raise WhalesnakeError(
                'Container was not yet created, but must exist.'
            )
        return method(*args, **kwargs)
    return wrap



class WhalesnakeError(Exception):
    pass



def containers(match=None, raw=False, **kwargs):
    '''
    match: Either an container ID or a container name.
    raw: Whether or not to return dicts instead of Container() instances
    
    Possible docker-py arguments and their defaults:
    
    quiet=False, all=False, trunc=True, latest=False,
    since=None, before=None, limit=-1, size=False
    
    '''
    ctns = dc.containers(**kwargs)
    if match:
        filtered = []
        for ctn in ctns:
            if ctn['Names'][0].find(match) is not -1 \
              or ctn['Id'].startswith(match):
                filtered.append(ctn)
        ctns = filtered
    if not raw:
        return [Container(ctn['Id']) for ctn in ctns]
    return ctns

def events(since, until):
    # returns a stream
    raise NotImplementedError

def images(match=None, raw=False, **kwargs):
    '''
    match: Either an container ID or a container name.
    raw: Whether or not to return dicts instead of Image() instances
    
    Possible docker-py arguments and their defaults:
    
    name=None, quiet=False, all=False, viz=False
    
    viz seems to be depracted.
    docker-py's 'name' argument behaves strangely: name='ubuntu' returns the
    expected image with [u'ubuntu:14.04', u'ubuntu:latest'], but
    name='ubuntu:latest' retuns [] ?! Use 'match' for more consistent results.
    
    '''
    # return image instances?
    imgs = dc.images(**kwargs)
    if match:
        filtered = []
        for img in imgs:
            if img['Id'].startswith(match):
                filtered.append(img)
                continue
            for name in img['RepoTags']:
                if name.find(match) is not -1:
                    filtered.append(img)
                    break
        imgs = filtered
    if not raw:
        return [Image(img['Id']) for img in imgs]
    return imgs

def info():
    return dc.info()

def login(user, *args, **kwargs):
    '''
    user: Username used for login.
    
    Possible docker-py arguments and their defaults:
    
    password=None, email=None, registry=None, reauth=False
    
    '''
    raise NotImplementedError
    dc.login(user, *args, **kwargs)

def ps(*args, **kwargs):
	# alias for 'containers'
    return containers(*args, **kwargs)

def search(match, official=None, automated=None, stars=False):
    '''
    match: Search query for the docker image registry.
    official: Show only official (True) or unofficial (False) builds.
      NOTE: Official images seem to always have 'automated' (called 'is_trusted'
      in the raw json) set to 'False'
    automated: Show only automated (True) or non-automated (False) builds.
    stars: Minimum number of stars.
    
    TODO: sort? return certain fields only?
    
    '''
    imgs = dc.search(match)
    
    if official is not None \
      or automated is not None \
      or stars is not False:
      
        filtered = []
        for img in imgs:         
            if official:
                if not official == img['is_official']:
                    continue
            
            if automated:
                if not automated == img['is_trusted']:
                    continue
            
            if stars:
                if not img['star_count'] >= stars:
                    continue
            
            filtered.append(img)
        return filtered
    return imgs

def version():
    return dc.version()

def ping():
    return dc.ping()



class Container(object):
    
    def __init__(self, name_or_cid):
        '''
        name_or_cid: Either the name of a new or existing container or a
            container ID of an existing container.
        
        One name per id
        One id per name
        
        '''
        self._passed_arg = name_or_cid
        self._passed_arg_type = None
        self.name = ''
        self.short_id, self.long_id = None, None
        
        try:
            # check if a cid was given
            self.short_id, self.long_id = check_docker_id(name_or_cid)
            self._passed_arg_type = 'ID'
        except ValueError:
            # not a cid, interpret as name, but check if empty
            if len(name_or_cid) is 0:
                raise  ValueError(
                    'Either a valid container id or a name must be given.'
                )
            
            check_container_name(name_or_cid)
            self.name = name_or_cid
            self._passed_arg_type = 'name'
        
        self._check_status()
        
        if self.short_id and not self.exists:
            # cid was given, but does not exist
            raise ValueError(
                'No container was found for id: {0}'.format(name_or_cid)
            )
    
    def __repr__(self):
        return 'Container(name_or_cid={0!r})'.format(self._passed_arg)
    
    def __str__(self):
        s = 'Container with name "{0}"'.format(self.name)
        if self.exists:
            s += ' and ID "{0}"'.format(self.long_id)
        return s
    
    def _check_status(self):
        '''
        Check status of the name/id and set the missing pieces
        
        '''
        # defaults
        self.exists = False
        self.created = False
        self.image = None
        self.ports = None
        self.command = None
        
        self.running = False
        self.paused = False
        
        for ctn in dc.containers(all=True):
            id_match = self.short_id and ctn['Id'].startswith(self.short_id)
            name_match = self.name and '/' + self.name in ctn['Names']
            if id_match or name_match:
                self.exists = True
                self.short_id, self.long_id = check_docker_id(ctn['Id'])
                # seems like there's only ever one name in the list
                self.name = ctn['Names'][0][1:] # strip leading '/'
                self.created = datetime.datetime.fromtimestamp(ctn['Created'])
                self.image = Image(ctn['Image'])
                self.ports = ctn['Ports']
                self.command = ctn['Command']
                
                # inspect gives a lot more information. write own method for it
                meta = self.inspect()
                self.running = meta['State']['Running']
                self.paused = meta['State']['Paused']
                break
    
    def run(self, image, command=None, create_conf={}, start_conf={}):
        '''
        short hand for create() + start() + necessary error handling, see:
        https://docs.docker.com/reference/api/
            docker_remote_api_v1.13/#31-inside-docker-run
        
        '''
        try:
            self.create(image, command=command, **create_conf)
        except ValueError as e:
            if e.args[0].find('No such image') is not -1:
                try:
                    i = Image(image)
                    i.pull()
                    # give it another shot
                    self.create(i, command=command, **create_conf)
                except Exception as ex:
                    raise WhalesnakeError(
                      'Unable to get image "{1}": {0}'.format(image, ex.args[0])
                    )
            else:
                raise e
        
        self.start(**start_conf)
    
    #######
    ## 'official' docker commands below
    ####
    
    def attach(self):
        raise NotImplementedError
        if not self.running:
            raise WhalesnakeError('Container is not running.')
    
    def commit(self, *args, **kwargs):
        '''
        Possible docker-py arguments and their defaults:
    
        repository=None, tag=None, message=None, author=None
        
        '''
        raise NotImplementedError
        res = dc.commit(self.long_id, *args, conf=None, **kwargs)
        return res # what does the output look like?
    
    def copy(self):
        raise NotImplementedError
        self._check_status()
    
    def create(self, image, command=None, **kwargs):
        '''
        image: Either a valid image id or name as string or an instance
            of .Image()
        command: Execute this inside the container
        
        Returns: : {u'Id': u'9164222a9d7...long_id_here', u'Warnings': None}
        
        Possible docker-py keyword arguments and their defaults:
    
        hostname=None, user=None, detach=False, stdin_open=False, tty=False,
        mem_limit=0, ports=None, environment=None, dns=None, volumes=None,
        volumes_from=None, network_disabled=False, entrypoint=None,
        cpu_shares=None, working_dir=None, memswap_limit=0
        
        '''
        if self.exists:
            raise WhalesnakeError(
                'Container() needs to be instantiated with an unassigned ' + \
                'name in order to allow for creations.'
            )
        
        if not isinstance(image, Image):
            image = Image(image)
            
        if not image.exists:
            raise ValueError(
                'No such image could be found: {0}\n' + \
                'Try to pull it first or just let Container.run() ' + \
                'take care of it.'.format(str(image))
            )
        
        out = dc.create_container(image.long_id, name=self.name,
                                  command=command, **kwargs)
        self._check_status()
        return out
    
    def diff(self):
        return dc.diff(self.long_id)
    
    def export(self, path):
        '''
        path: String containing the filepath where the .tar should go
        Returns: Nothing
        
        TODO: 
        - path could also be a file object
        - gzip flag
        
        '''
        if not self.exists:
            raise WhalesnakeError('Container was not yet created.')
        tar = dc.export(self.long_id) # returns a 'tar' stream
        with open(path, 'wb') as f:
            while True:
                l = tar.read(52428800) # 50MB
                if not l:
                    break
                f.write(l)
    
    def inspect(self):
        return dc.inspect_container(self.long_id)
    
    def kill(self, signal=None):
        if not self.running:
            raise WhalesnakeError('Container is not running.')
        dc.kill(self.long_id, signal)
        self._check_status()

    def logs(self, *args, **kwargs):
        '''
        Returns: what the container has written to stdout and stderr
        (by default)
        
        Possible docker-py arguments and their defaults:
    
        stdout=True, stderr=True, stream=False, timestamps=False
        
        '''
        if 'stream' in kwargs.keys():
            # take care of stream. just pass it through?
            raise NotImplementedError
        return dc.logs(self.long_id, *args, **kwargs)
    
    def port(self, private_port):
        '''
        Returns the host port and ip for the given 'private_port':
        [{u'HostPort': u'5000', u'HostIp': u'0.0.0.0'}]
        
        '''
        if not self.exists:
            raise WhalesnakeError('Container was not yet created.')
        return dc.port(self.long_id, private_port)
    
    def restart(self, timeout=None):
        if not self.exists:
            raise WhalesnakeError('Container was not yet created.')
        if self.running:
            raise WhalesnakeError('Container is running already.')
        dc.restart(self.long_id, timeout)
        self._check_status()
    
    def remove(self, force=False, **kwargs):
        '''
        force: force removal, e.g. when ctn is running
        
        Possible docker-py arguments and their defaults:
    
        link=False, volumes=False
        
        '''
        if not self.exists:
            raise WhalesnakeError('Container was not yet created.')
        if self.running and not force:
            raise WhalesnakeError(
                'Container is running. Use force=True to remove anyway.'
            )
        dc.remove_container(self.long_id, force=force, **kwargs)
        self._check_status()
    
    def start(self, *args, **kwargs):
        '''
        Returns: nothing
        
        Possible docker-py arguments and their defaults:
    
        binds=None, port_bindings=None, lxc_conf=None,
        publish_all_ports=False, links=None, privileged=False,
        dns=None, dns_search=None, volumes_from=None, network_mode=None
        
        '''
        if not self.exists:
            raise WhalesnakeError('Container was not yet created.')
        if self.running:
            raise WhalesnakeError('Container is running already.')
        dc.start(self.long_id, *args, **kwargs)
        self._check_status()
    
    def stop(self, **kwargs):
        if not self.running:
            raise WhalesnakeError('Container is not running.')
        dc.stop(self.long_id, **kwargs)
        self._check_status()
    
    def top(self):
        # docker-py is lacking support for ps options
        if not self.running:
            raise WhalesnakeError('Container is not running.')
        return dc.top(self.long_id)
    
    def wait(self):
        return dc.wait(self.long_id)



class Image(object):

    def __init__(self, repo_or_iid):
        '''
        Multiple tags per id
        One id per tag
        Assumes :latest if no tag was given for repo
        
        '''
        self._passed_arg = repo_or_iid
        self.names = []
        self.initial_name = ''
        self.short_id, self.long_id = None, None
        self.build_log = ''
            
        try:
            # check if an iid was given
            self.short_id, self.long_id = check_docker_id(repo_or_iid)
        except ValueError:
            # not an iid, interpret as name, but check if empty
            if len(repo_or_iid) is 0:
                raise ValueError(
                    'Either a valid image id or "[namespace/]repo[:tag]" ' + \
                    'must be given.'
                )
            
            ns, repo, tag = check_image_name(repo_or_iid)
            
            if not tag:
                # assume we want the latest image from 'repo'
                repo_or_iid += ':latest'
            self.names.append(repo_or_iid)
            self.initial_name = repo_or_iid
        
        self._check_status()
        
        if self.short_id and not self.exists:
            raise ValueError(
                'No image was found for id: {0}'.format(repo_or_iid)
            )
    
    def __repr__(self):
        return 'Image(repo_or_iid={0!r})'.format(self._passed_arg)
    
    def __str__(self):
        if self.exists:
            s = 'Image with names "{0}"'.format(', '.join(self.names))
            s += ' and ID "{0}"'.format(self.long_id)
        else:
            s = 'Image with name "{0}"'.format(self.initial_name)
        return s
    
    def _check_status(self):
        '''
        Check status of the tag/id and set the missing pieces
        
        '''
        # defaults
        self.exists = False
        self.created = False
        self.parent_id = None
        self.virtual_size = None
        
        for img in dc.images():
            id_match = self.short_id and img['Id'].startswith(self.short_id)
            tag_match = self.initial_name \
                            and self.initial_name in img['RepoTags']
            if id_match or tag_match:
                self.exists = True
                self.short_id, self.long_id = check_docker_id(img['Id'])
                self.names = img['RepoTags'] # add all tags
                self.created = datetime.datetime.fromtimestamp(img['Created'])
                self.parent_id = img['ParentId']
                # docker uses base 10 for sizes i.e. 1kB = 1000B
                self.virtual_size = img['VirtualSize'] # in Bytes
                # img['Size'] seems to always be 0
                break
    
    #######
    ## 'official' docker commands below
    ####
    
    def build(self, build_src, build_type, rm=True, **kwargs):
        '''
        build_src: Object matching the build_type (open file, file-like obj ...)
        build_type: The type of build_src. One of:
            'tar', 'tar.gz', 'file', 'url', 'path', 'github', 'git'
        rm: Remove intermediate containers. Defaults to True on the command
            line, but not in docker-py
            
        Returns: Nothing
        
        Possible docker-py arguments and their defaults:
        quiet=False, nocache=False, timeout=None
        
        '''
        # add option to 'print' the output received through stream
        # optional: autodetect type (w/ https://github.com/ahupp/python-magic ?)
        
        if self.exists:
            raise WhalesnakeError(
                'Image() needs to be instantiated with a name instead of ' + \
                'an image ID in order to allow for builds.'
            )
        
        args = {
            'tag': self.initial_name,
            'rm': rm
        }
        
        if build_type in ['tar', 'tar.gz']:
            args['fileobj'] = build_src
            args['custom_context'] = True
            if build_type == 'tar.gz':
                args['encoding'] = 'gzip'
        elif build_type == 'file':
            args['fileobj'] = build_src
        elif build_type in ['url', 'path', 'github', 'git']:
            args['path'] = build_src
        else:
            raise ValueError(
                'Build type "{0}" is not supported.'.format(build_type)
            )
            
        if kwargs:
            args.update(kwargs)
            
        res = dc.build(**args)
        
        # https://github.com/docker/docker-py/issues/255
        # lines w/ 'stream' as JSON key only contain information about
        # the build process, not about pulling images from the registry etc.
        lines = [line for line in res]
        try:
            parsed_lines = [json.loads(e).get('stream', '') for e in lines]
        except ValueError:
            # sometimes all the data is sent on a single line ????
            #
            # ValueError: Extra data: line 1 column 87 - line 1 column
            # 33268 (char 86 - 33267)
            line = lines[0]
            # This ONLY works because every line is formatted as
            # {"stream": STRING}
            parsed_lines = [
                json.loads(obj).get('stream', '') for obj in
                re.findall('{\s*"stream"\s*:\s*"[^"]*"\s*}', line)
            ]
        
        self.build_log = ''.join(parsed_lines)
        # search for success message
        search = r'^Successfully built ([0-9a-f]{12})\n$'
        status = parsed_lines[-1]
        match = re.search(search, status)
        if match:
            # update meta data
            self._check_status()
            return
        
        elif status == '' and len(lines) is 1:
            err = lines[0]
            if 'errorDetail' in err:
                msg = json.loads(err)['errorDetail']['message']
                raise WhalesnakeError(
                    'Build failed: {0}'.format(msg)
                )
        
        # something else went wrong - dump everything we got back
        raise WhalesnakeError('Build failed:\n{0}'.format(res))
    
    def history(self):
        if not self.exists:
            raise WhalesnakeError('Image does not yet exist')
        hist = dc.history(self.long_id)
        return json.loads(hist)
    
    def import_(self):
        raise NotImplementedError
        self._check_status()
    
    def inspect(self):
        if not self.exists:
            raise WhalesnakeError('Image does not yet exist')
        return dc.inspect_image(self.long_id)
    
    def pull(self, force=False):
        if not self.exists or force:
            jsn = dc.pull(self.initial_name)
            msg = json.loads(jsn.split('\r\n')[-2])
            if 'errorDetail' in msg:
                raise ValueError(msg['errorDetail']['message'])
            self._check_status()
        else:
            raise WhalesnakeError(
                'Image exists. Use force=True to pull anyway.'
            )
    
    def push(self):
        # might requrire login?
        raise NotImplementedError
        if not self.exists:
            raise WhalesnakeError('Image does not yet exist')
    
    def remove(self, force=False, no_prune=False):
        '''
        Removes the image.
        
        force: Needed for removal, if the image has multiple tags
        no_prune: Do not delete untagged parents
        
        Returns: Nothing
        
        '''
        if not self.exists:
            raise WhalesnakeError('Image does not yet exist')
        
        if len(self.names) > 1:
            if force:
                # why does docker only untag and not delete images even though
                # the force flag is set?
                for name in self.names:
                    dc.remove_image(self.long_id, force, no_prune)
            else:
                raise WhalesnakeError(
                    'Image is tagged in multiple repositories. ' + \
                    'Use force=True to remove anyway'
                )
        else:
            dc.remove_image(self.long_id, force, no_prune)
        
        self._check_status()
    
    def tag(self, tags, force=False):
        '''
        tags: string or list of strings, that the image should be tagged with
        force: Enforce the tag
        
        Returns: nothing
        
        '''
        if not self.exists:
            raise WhalesnakeError('Image does not yet exist')
        if isinstance(tags, basestring):
            tags = [tags, ]
        for tag in tags:
            ns, repo, tag = check_image_name(tag)
            if ns:
                repo = ns + '/' + repo
            dc.tag(self.long_id, repository=repo, tag=tag, force=force)
        self._check_status()
    
    def untag(self, tags=None):
        '''
        Untags are only possible when instantiated with a name and the total
        number of tags is greater than 1. Anything else would result in an image
        removal.
        
        tags: A string or a list of strings. They will be removed as tags from
            the underlying image id .
        
        Returns: nothing
        
        '''
        if not self.exists:
            raise WhalesnakeError('Image does not yet exist')
            
        if tags:
            if isinstance(tags, basestring):
                tags = [tags, ]
            if not len(tags) < len(self.names):
                raise WhalesnakeError(
                    'Only n-1 untags are possible, where n is the total ' + \
                    'number of existing tags'
                )
            for tag in tags:
                # assume latest if no actual tag is given
                if not ':' in tag:
                    tag += ':latest'
                if not tag in self.names:
                    raise ValueError(
                        'Tag does not exist: "{0}"'.format(tag)
                    )
                dc.remove_image(tag)
                self._check_status()
                
        elif self.initial_name in self.names and len(self.names) > 1:
            dc.remove_image(self.initial_name)
            self._check_status()
            #self.initial_name = ''
            
        else:
            raise WhalesnakeError(
                'Either not instantiated with a name or number of ' + \
                'existing tags is < 2'
            )

