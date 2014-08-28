#!/usr/bin/env python
# -*- coding: utf-8 -*-

import io
import os
import time
import tarfile
import datetime
import tempfile

import docker
from pytest import raises

import whalesnake as ws

ws.connect()
c = docker.Client(base_url='unix://var/run/docker.sock',
                  version='1.13',
                  timeout=15)



dedicated_testing_image = None
TEST_IMAGE_ID = None
TEST_IMAGE_NAME = None
TEST_CONTAINER_ID = None
TEST_CONTAINER_NAME = 'whalesnake_test_ctn0'

def setup_module(self):
    global dedicated_testing_image
    global TEST_IMAGE_ID
    global TEST_IMAGE_NAME
    global TEST_CONTAINER_ID
    get_dedicated = True
    
    imgs = c.images()
    if imgs:
        # use an existing image. sort by lowest footprint
        imgs = sorted(imgs, key=lambda x: x['VirtualSize'])
        # pick one that has no entrypoint set
        for img in imgs:
            ep = c.inspect_image(img['Id'])['ContainerConfig']['Entrypoint']
            if ep is None:
                get_dedicated = False
                break
        
    if not get_dedicated:
        TEST_IMAGE_ID = img['Id']
        TEST_IMAGE_NAME = img['RepoTags'][0]
    else:
        # no images present? get busybox
        dedicated_testing_image = True
        TEST_IMAGE_NAME = 'busybox:latest'
        c.pull(TEST_IMAGE_NAME)
        TEST_IMAGE_ID = c.images()[0]['Id']
        
    TEST_CONTAINER_ID = c.create_container(TEST_IMAGE_NAME,
                                           name=TEST_CONTAINER_NAME,
                                           command='sleep 999')['Id']
        

def teardown_module(self):
    for ctn in c.containers(all=True):
        name = ctn['Names'][0][1:]
        if name.startswith('whalesnake_test_'):
            c.remove_container(ctn['Id'], force=True)
    
    for img in c.images():
        for name in img['RepoTags']:
            if name.startswith('whalesnake_test_'):
                c.remove_image(img['Id'], force=True)
    
    if dedicated_testing_image:
        c.remove_image(TEST_IMAGE_NAME)
        
        
        
class Test_check_docker_id:

    def test_valid_ids(self):
        v = 'e0f46ff95af76727b8f5de87825f88a0cd1cbad36fad2e2bbd355b4904da1960'
        short_id, long_id = ws.check_docker_id(v)
        assert short_id == 'e0f46ff95af7'
        assert long_id == v
        
        v = 'e0f46ff95af7'
        short_id, long_id = ws.check_docker_id(v)
        assert short_id == v
        assert long_id is None

    def test_length(self):
        # 63 chars
        v ='e0f46ff95af76727b8f5de87825f88a0cd1cbad36fad2e2bbd355b4904da196'
        with raises(ValueError):
            ws.check_docker_id(v)
        
        v = ''
        with raises(ValueError):
            ws.check_docker_id(v)
    
    def test_non_hex_values(self):
        with raises(ValueError):
            ws.check_docker_id('gggggggggggg')
        with raises(ValueError):
            ws.check_docker_id('00000000000q')
        with raises(ValueError):
            ws.check_docker_id(
             'ccccccccccccccccccccccccccccccccycccccccccccccccccccccccccccccccc'
            )



class Test_check_image_name:
    
    def test_valid_names(self):
        # min namespace length: 4
        ns, repo, tag = ws.check_image_name(
            'abcd/reponame:tag'
        )
        assert ns == 'abcd'
        assert repo == 'reponame'
        assert tag == 'tag'
        
        # max namespace length: 30
        ns, repo, tag = ws.check_image_name(
            'abcdefghijklmnopqrstuvwxyz789_/reponame:tag'
        )
        assert ns == 'abcdefghijklmnopqrstuvwxyz789_'
        assert repo == 'reponame'
        assert tag == 'tag'
        
        # no tag
        ns, repo, tag = ws.check_image_name(
            'abcd/reponame'
        )
        assert ns == 'abcd'
        assert repo == 'reponame'
        assert tag is None
        
        # no namespace
        ns, repo, tag = ws.check_image_name(
            'reponame:tag'
        )
        assert ns is None
        assert repo == 'reponame'
        assert tag == 'tag'
        
        # no tag, no namespace
        ns, repo, tag = ws.check_image_name(
            'reponame-_.0123'
        )
        assert ns is None
        assert repo == 'reponame-_.0123'
        assert tag is None
    
    def test_invalid_names(self):
        # below min namespace length: 3
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                'abc/reponame:tag'
            )
        
        # above max namespace length: 31
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                'abcdefghijklmnopqrstuvwxyz7890_/reponame:tag'
            )
        
        # invalid char in namespace
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                'abcd*/reponame'
            )
        
        # invalid char in repo
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                'abcd/repo#name'
            )
        
        # more than one /
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                'abcd/repo/name'
            )
        
        # more than one :
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                'abcd:repo:name'
            )
        
        # missing repo
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                'abcd/'
            )
        
        # missing ns
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                '/repo'
            )
        
        # missing tag
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                'abcd/repo:'
            )
        
        # missing tag
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                'repo:'
            )
        
        # missing repo
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                ':tag'
            )
        
        # empty repo
        with raises(ValueError):
            ns, repo, tag = ws.check_image_name(
                ''
            )



class Test_check_container_name:

    def test_valid_names(self):
        ws.check_container_name('aA0_.-')
        ws.check_container_name('a')
        ws.check_container_name('_')

    def test_invalid_names(self):
        with raises(ValueError):
            ws.check_container_name('aA0_.-$$$')
        with raises(ValueError):
            ws.check_container_name('')
        with raises(ValueError):
            ws.check_container_name('_/-')



class Test_general_docker_commands:

    def test_images(self):
        res = ws.images(raw=False)
        assert isinstance(res, list)
        
        res = ws.images(TEST_IMAGE_NAME, raw=False)
        assert isinstance(res, list)
        assert len(res) is 1
        assert isinstance(res[0], ws.Image)
        assert res[0].long_id == TEST_IMAGE_ID
        
        res = ws.images(TEST_IMAGE_ID, raw=False)
        assert isinstance(res, list)
        assert len(res) is 1
        assert isinstance(res[0], ws.Image)
        assert res[0].long_id == TEST_IMAGE_ID
        
        # test raw=True
        res = ws.images(TEST_IMAGE_ID, raw=True)
        assert isinstance(res, list)
        assert len(res) is 1
        assert not isinstance(res[0], ws.Image)
        assert res[0]['Id'] == TEST_IMAGE_ID

    def test_containers(self):
        res = ws.containers()
        assert isinstance(res, list)
        
        # container is inactive, thus all=True
        res = ws.containers(TEST_CONTAINER_NAME, raw=False, all=True)
        assert isinstance(res, list)
        assert len(res) is 1
        assert isinstance(res[0], ws.Container)
        assert res[0].long_id == TEST_CONTAINER_ID
        assert res[0].name == TEST_CONTAINER_NAME
        
        res = ws.containers(TEST_CONTAINER_ID, raw=False, all=True)
        assert isinstance(res, list)
        assert len(res) is 1
        assert isinstance(res[0], ws.Container)
        assert res[0].long_id == TEST_CONTAINER_ID
        assert res[0].name == TEST_CONTAINER_NAME
        
        # test raw=True
        res = ws.containers(TEST_CONTAINER_ID, raw=True, all=True)
        assert isinstance(res, list)
        assert len(res) is 1
        assert not isinstance(res[0], ws.Container)
        assert res[0]['Id'] == TEST_CONTAINER_ID

    def test_info(self):
        res = ws.info()
        assert 'ExecutionDriver' in res.keys()

    def test_ps(self):
        res = ws.ps()
        assert isinstance(res, list)

    # mock this?
    def test_search(self):
        res = ws.search('dstat')
        assert isinstance(res, list)
        assert len(res) >= 1
        
        res = ws.search('unlikely_name__for_a__container')
        assert isinstance(res, list)
        assert len(res) is 0
        
        res = ws.search('postgis', automated=True, stars=1)
        assert isinstance(res, list)
        assert len(res) >= 1
        assert res[0]['star_count'] >= 1
        assert res[0]['is_trusted'] is True

    def test_version(self):
        res = ws.version()
        assert 'Arch' in res.keys()

    def test_ping(self):
        assert ws.ping() == 'OK'



class Test_Container:
    
    def test_instantiation(self):
        ctn = ws.Container('whalesnake_test_ctn1')
        assert ctn.exists is False
        assert ctn.short_id is None
        assert ctn.name is 'whalesnake_test_ctn1'
        
        # get existing one by long id
        ctn = ws.Container(TEST_CONTAINER_ID)
        assert ctn.exists is True
        assert ctn.long_id == TEST_CONTAINER_ID
        assert ctn.name == TEST_CONTAINER_NAME
        assert isinstance(ctn.image, ws.Image)
        assert TEST_IMAGE_NAME in ctn.image.names
        d = datetime.datetime.now() - datetime.timedelta(seconds=20)
        assert ctn.created > d
        assert ctn.ports == []
        assert ctn.command is not None
        
        # get existing one by name
        ctn = ws.Container(TEST_CONTAINER_NAME)
        assert ctn.exists is True
        assert ctn.long_id == TEST_CONTAINER_ID
        assert ctn.name == TEST_CONTAINER_NAME
        
        with raises(TypeError):
            ctn = ws.Container()
        with raises(ValueError):
            ctn = ws.Container('')
        with raises(ValueError) as e:
            # valid short id, but not existent
            ctn = ws.Container('abcdef123456')
        assert e.value.message.startswith('No container was found')
        with raises(ValueError):
            # invalid character: /
            ctn = ws.Container('abcdef/')
    
    def test__repr__(self):
        ctn = ws.Container(TEST_CONTAINER_NAME)
        assert repr(ctn) == 'Container(name_or_cid={0!r})'.format(
            TEST_CONTAINER_NAME
        )
        
        ctn = ws.Container(TEST_CONTAINER_ID)
        assert repr(ctn) == 'Container(name_or_cid={0!r})'.format(
            TEST_CONTAINER_ID
        )
    
    def test__str__(self):
        ctn = ws.Container(TEST_CONTAINER_NAME)
        assert str(ctn) == 'Container with name "{0}" and ID "{1}"'.format(
            TEST_CONTAINER_NAME, TEST_CONTAINER_ID
        )
        
        ctn = ws.Container('non_existing_container')
        s = 'Container with name "{0}"'.format('non_existing_container')
        assert str(ctn) == s
    
    def test_create(self):
        ctn = ws.Container('whalesnake_test_ctn2')
        res = ctn.create(TEST_IMAGE_ID, 'sleep 999')
        assert 'Id' in res
        assert 'Warnings' in res
        assert res['Warnings'] is None
        assert res['Id'] == ctn.long_id
        assert ctn.exists is True
        assert ctn.command is not None
        
        # test passing an Image() instance
        ctn = ws.Container('whalesnake_test_ctn3')
        img = ws.Image(TEST_IMAGE_ID)
        res = ctn.create(img, 'sleep 999')
        assert 'Id' in res
        assert 'Warnings' in res
        assert res['Warnings'] is None
        assert res['Id'] == ctn.long_id
        assert ctn.exists is True
        assert ctn.command is not None
        
        # try to create, based on existing ID
        with raises(ws.WhalesnakeError):
            ctn = ws.Container(TEST_CONTAINER_ID)
            ctn.create(TEST_IMAGE_ID)
            
        # try to create, based on existing name
        with raises(ws.WhalesnakeError):
            ctn = ws.Container(TEST_CONTAINER_NAME)
            ctn.create(TEST_IMAGE_ID)
        
        # cancel creation if image does not exist
        ctn = ws.Container('whalesnake_test_ctn4')
        with raises(ValueError):
            # invalid id
            ctn.create('abcdefghijkl')
        with raises(ValueError) as e:
            i = ws.Image('non_existing_image')
            ctn.create(i)
        assert e.value.message.startswith('No such image could be found')
        with raises(ValueError) as e:
            ctn.create('non_existing_image_name')
        assert e.value.message.startswith('No such image could be found')
        with raises(ValueError):
            ctn.create('arko/sinatra') # unlikely to exist, only few DL's
    
    def test_diff(self):
        ctn = ws.Container(TEST_CONTAINER_ID)
        assert isinstance(ctn.diff(), list)
    
    def test_export(self):
        ctn = ws.Container(TEST_CONTAINER_ID)
        td = tempfile.gettempdir()
        tf = td + '/{0}.tar'.format(TEST_CONTAINER_NAME)
        ctn.export(tf)
        assert tarfile.is_tarfile(tf) is True
        os.remove(tf)
        
        ctn = ws.Container('non_existing_container')
        with raises(ws.WhalesnakeError):
            ctn.export(td + '/x.tar')
    
    def test_inspect(self):
        ctn = ws.Container(TEST_CONTAINER_ID)
        res = ctn.inspect()
        assert isinstance(res, dict)
        assert 'State' in res
        assert 'Name' in res
        assert res['Name'][1:] == TEST_CONTAINER_NAME
    
    def test_logs(self):
        ctn = ws.Container(TEST_CONTAINER_ID)
        assert isinstance(ctn.logs(), basestring)
    
    def test_port(self):
        port_bindings = {
            1111: ('127.0.0.1', '4567'),
            2222: ('127.0.0.1', '4568')
        }
        
        ctn = ws.Container('whalesnake_test_ctn5')
        ctn.create(TEST_IMAGE_ID, 'sleep 999', ports=port_bindings.keys())
        ctn.start(port_bindings=port_bindings)
        p = ctn.port(1111)
        assert isinstance(p, list)
        assert isinstance(p[0], dict)
        assert p[0]['HostPort'] == '4567'
        p = ctn.port(2222)
        assert p[0]['HostPort'] == '4568'
        
        ctn = ws.Container('non_existing_container')
        with raises(ws.WhalesnakeError):
            ctn.port(1111)
    
    def test_start_stop_restart_kill(self):
        ctn = ws.Container('whalesnake_test_ctn6')
        ctn.create(TEST_IMAGE_ID, 'sleep 999')
        assert ctn.exists is True
        ctn.start()
        # (re)starting again while already running should raise
        with raises(ws.WhalesnakeError):
            ctn.start()
        with raises(ws.WhalesnakeError):
            ctn.restart()
        assert ctn.running is True
        ctn.stop()
        assert ctn.running is False
        ctn.restart()
        assert ctn.running is True
        ctn.kill()
        assert ctn.running is False
        
        
        ctn = ws.Container('non_existing_container')
        with raises(ws.WhalesnakeError):
            ctn.start()
        ctn = ws.Container('non_existing_container')
        with raises(ws.WhalesnakeError):
            ctn.stop()
        ctn = ws.Container('non_existing_container')
        with raises(ws.WhalesnakeError):
            ctn.restart()
        ctn = ws.Container('non_existing_container')
        with raises(ws.WhalesnakeError):
            ctn.kill()
    
    def test_remove(self):
        ctn = ws.Container('whalesnake_test_ctn98')
        ctn.create(TEST_IMAGE_ID, 'sleep 999')
        assert ctn.exists is True
        ctn.remove()
        assert ctn.exists is False
        
        ctn = ws.Container('whalesnake_test_ctn99')
        ctn.create(TEST_IMAGE_ID, 'sleep 999')
        assert ctn.exists is True
        ctn.start()
        assert ctn.running is True
        # takes like 5 secs, no matter if force=True or not
        with raises(ws.WhalesnakeError):
            ctn.remove() 
        ctn.remove(force=True)
        assert ctn.running is False
        assert ctn.exists is False
        
        ctn = ws.Container('non_existing_container')
        with raises(ws.WhalesnakeError):
            ctn.remove()
    
    def test_top(self):
        ctn = ws.Container('whalesnake_test_ctn7')
        cmd = 'sleep 999'
        ctn.create(TEST_IMAGE_ID, cmd)
        ctn.start()
        t = ctn.top()
        assert len(t['Processes']) is 1
        assert t['Processes'][0][-1] == cmd
        ctn.stop()
        
        ctn = ws.Container('non_existing_container')
        with raises(ws.WhalesnakeError):
            ctn.top()
    
    def test_wait(self):
        pass
    
    def test_run(self):
        ctn = ws.Container('whalesnake_test_ctn8')
        ctn.run(TEST_IMAGE_ID, 'sleep 999')
        assert ctn.exists is True
        assert ctn.running is True
        ctn.stop()
        
        # try running with an existing image that can be pulled
        ctn = ws.Container('whalesnake_test_ctn96')
        ctn.run('greglearns/dietfs', 'sleep 999')
        assert ctn.exists is True
        assert ctn.running is True
        ctn.stop()
        
        # try running with a non-existing image that also can NOT be pulled
        img = 'non_existent_image'
        ctn = ws.Container('whalesnake_test_ctn97')
        with raises(ws.WhalesnakeError) as e:
            ctn.run(img, 'sleep 999')
        assert e.value.message.find('Unable to get image') is not -1
        assert ctn.exists is False
        assert ctn.running is False



class Test_Image:

    def get_dockerfile(self, image):
        # strings need to be fed to io.StringIO and be unicode!
        df = u'FROM {0}\n' + \
             u'MAINTAINER whalesnake\n' + \
             u'RUN echo "test" > /tmp/test\n'
             
        df = df.format(image)
        return len(df), io.StringIO(df)
    
    def test_instantiation(self):
        img = ws.Image('whalesnake_test_img1')
        assert img.exists is False
        assert img.short_id is None
        assert img.initial_name == 'whalesnake_test_img1:latest'
        assert len(img.names) is 1
        assert img.names[0] == 'whalesnake_test_img1:latest'
        
        # get existing one by long id
        img = ws.Image(TEST_IMAGE_ID)
        assert img.exists is True
        assert img.long_id == TEST_IMAGE_ID
        assert img.initial_name == ''
        assert len(img.names) >= 1
        assert TEST_IMAGE_NAME in img.names
        assert isinstance(img.created, datetime.datetime)
        # don't check parent_id, can be empty with some images
        #ws.check_docker_id(img.parent_id)
        assert isinstance(img.virtual_size, int)
        
        # get existing one by name
        img = ws.Image(TEST_IMAGE_NAME)
        assert img.exists is True
        assert img.long_id == TEST_IMAGE_ID
        assert img.initial_name == TEST_IMAGE_NAME
        assert len(img.names) >= 1
        assert TEST_IMAGE_NAME in img.names
        
        with raises(TypeError):
            img = ws.Image()
        with raises(ValueError):
            img = ws.Image('')
        with raises(ValueError) as e:
            # valid short id, but not existent
            img = ws.Image('abcdef123456')
        assert e.value.message.startswith('No image was found')
        with raises(ValueError):
            # invalid character: /
            img = ws.Image('abcdef/')
    
    def test__repr__(self):
        img = ws.Image(TEST_IMAGE_NAME)
        assert repr(img) == 'Image(repo_or_iid={0!r})'.format(TEST_IMAGE_NAME)
        
        img = ws.Image(TEST_IMAGE_ID)
        assert repr(img) == 'Image(repo_or_iid={0!r})'.format(TEST_IMAGE_ID)
    
    def test__str__(self):
        img = ws.Image(TEST_IMAGE_NAME)
        s = 'Image with names "{0}" and ID "{1}"'.format(
            TEST_IMAGE_NAME, TEST_IMAGE_ID
        )
        assert str(img) == s
        
        img = ws.Image(TEST_IMAGE_ID)
        s = 'Image with names "{0}" and ID "{1}"'.format(
            TEST_IMAGE_NAME, TEST_IMAGE_ID
        )
        assert str(img) == s
        
        img = ws.Image('non_existing_image')
        s = 'Image with name "{0}"'.format('non_existing_image:latest')
        assert str(img) == s
    
    # somehow mock this?
    def test_pull(self):
        img = ws.Image('jpetazzo/busybox:latest')
        img.pull()
        assert img.exists is True
        with raises(ws.WhalesnakeError):
            img.pull()
        assert img.exists is True
        # test force flag
        #img.pull(force=True)
        #assert img.exists is True
        
        img = ws.Image('google/loves_bing:latest')
        with raises(ValueError):
            img.pull()
        assert img.exists is False
    
    def test_remove(self):
        img = ws.Image('jpetazzo/busybox:latest')
        img.remove()
        assert img.exists is False
        
        img = ws.Image('non_existing_image')
        with raises(ws.WhalesnakeError):
            img.remove()
            
        f_size, f_obj = self.get_dockerfile(TEST_IMAGE_NAME)
        img = ws.Image('whalesnake_test_img9')
        img.build(f_obj, 'file')
        img.tag('whalesnake_test_second_tag')
        assert len(img.names) == 2
        # need force flag to remove an image with two tags
        with raises(ws.WhalesnakeError):
            img.remove()
        assert img.exists is True
        img.remove(force=True)
        assert img.exists is False
    
    def test_build(self):
        # test with:
        # url, github-url
        
        # invalid 'FROM' statement: should trigger appropriate error
        f_size, f_obj = self.get_dockerfile('***')
        img = ws.Image('whalesnake_test_img2')
        with raises(ws.WhalesnakeError) as e:
            img.build(f_obj, 'file')
        assert e.value.message.find('Invalid repository name (***)') is not -1
        assert img.exists is False
        
        # build from file object. use unknown, locally available test image
        # also test 'quiet' as additional kwarg
        f_size, f_obj = self.get_dockerfile(TEST_IMAGE_NAME)
        img = ws.Image('whalesnake_test_img3')
        img.build(f_obj, 'file', quiet=True)
        assert img.exists is True
        d = datetime.datetime.now() - datetime.timedelta(seconds=60)
        assert img.created > d
        assert isinstance(img.build_log, basestring)
        assert len(img.build_log) > 0
        assert 'whalesnake_test_img3:latest' in img.names
        img.remove()
        assert img.exists is False
        
        # build from .tar file
        f_size, f_obj = self.get_dockerfile(TEST_IMAGE_NAME)
        context = io.StringIO()
        tar = tarfile.open(mode='w|', fileobj=context)
        info = tarfile.TarInfo(name=u"Dockerfile")
        info.size = f_size
        tar.addfile(tarinfo=info, fileobj=f_obj)
        tar.close()
        context.seek(0)
        img = ws.Image('whalesnake_test_img4')
        img.build(context, 'tar')
        assert img.exists is True
        assert 'whalesnake_test_img4:latest' in img.names
        img.remove()
        assert img.exists is False
        
        # build from .tar.gz file
        f_size, f_obj = self.get_dockerfile(TEST_IMAGE_NAME)
        context = io.BytesIO() # gzip outputs a byte stream
        tar = tarfile.open(mode='w|gz', fileobj=context)
        info = tarfile.TarInfo(name=u"Dockerfile")
        info.size = f_size
        tar.addfile(tarinfo=info, fileobj=f_obj)
        tar.close()
        context.seek(0)
        img = ws.Image('whalesnake_test_img5')
        img.build(context, 'tar.gz')
        assert img.exists is True
        assert 'whalesnake_test_img5:latest' in img.names
        img.remove()
        assert img.exists is False
        
        # build from path to a dir containing a Dockerfile
        f_size, f_obj = self.get_dockerfile(TEST_IMAGE_NAME)
        td = tempfile.gettempdir() + '/whalesnake_test'
        tf = td + '/Dockerfile'
        os.mkdir(td)
        with open(tf, 'w') as f:
            f.write(f_obj.read())
        img = ws.Image('whalesnake_test_img6')
        img.build(td, 'path')
        assert img.exists is True
        assert 'whalesnake_test_img6:latest' in img.names
        img.remove()
        assert img.exists is False
        os.remove(tf)
        os.rmdir(td)
        
        # fail if build_type is unsupported
        img = ws.Image('whalesnake_test_img7')
        with raises(ValueError) as e:
            img.build('some_tag', 'unknown')
        assert img.exists is False
        assert e.value.message == 'Build type "unknown" is not supported.'
    
    def test_history(self):
        img = ws.Image(TEST_IMAGE_NAME)
        hist = img.history()
        assert isinstance(hist, list)
        assert 'CreatedBy' in hist[0]
        
        img = ws.Image('non_existing_image')
        with raises(ws.WhalesnakeError):
            img.history()
    
    def test_inspect(self):
        img = ws.Image(TEST_IMAGE_NAME)
        ins = img.inspect()
        assert isinstance(ins, dict)
        assert 'Architecture' in ins
        
        img = ws.Image('non_existing_image')
        with raises(ws.WhalesnakeError):
            img.inspect()
    
    def test_tag_untag(self):
        f_size, f_obj = self.get_dockerfile(TEST_IMAGE_NAME)
        
        img = ws.Image('whalesnake_test_img8')
        img.build(f_obj, 'file')
        assert 'whalesnake_test_img8:latest' in img.names
        
        # tag with string
        img.tag('whalesnake_test_repo:plus_tag')
        assert 'whalesnake_test_repo:plus_tag' in img.names
        # tag with list
        img.tag([
            'whalesnake_test_another_repo',
            'whalesnake_test_namespace/repo:tag',
            'whalesnake_test_one_more',
            'whalesnake_test_number_4'
        ])
        assert 'whalesnake_test_another_repo:latest' in img.names
        assert 'whalesnake_test_namespace/repo:tag' in img.names
        assert 'whalesnake_test_one_more:latest' in img.names
        assert 'whalesnake_test_number_4:latest' in img.names
        # should validate tags before sending them to the docker daemon
        with raises(ValueError):
            img.tag('whalesnake_test_inv*alid/name#')
            
        img2 = ws.Image('non_existing_image')
        with raises(ws.WhalesnakeError):
            img2.tag('test')
        
        
        # untag initial tag
        assert img.initial_name == 'whalesnake_test_img8:latest'
        img.untag()
        assert img.exists is True
        assert not 'whalesnake_test_img8:latest' in img.names
        #assert img.initial_name == ''
        # untag with string
        img.untag('whalesnake_test_repo:plus_tag')
        assert img.exists is True
        assert not 'whalesnake_test_repo:plus_tag' in img.names
        # untag with list, should assume :latest where no tag is given
        img.untag([
            'whalesnake_test_another_repo',
            'whalesnake_test_namespace/repo:tag'
        ])
        assert img.exists is True
        assert not 'whalesnake_test_another_repo:latest' in img.names
        assert not 'whalesnake_test_namespace/repo:tag' in img.names
        
        # there should be 2 remaining tags now
        assert len(img.names) is 2
        # try to untag them both
        with raises(ws.WhalesnakeError):
            img.untag([
                'whalesnake_test_one_more',
                'whalesnake_test_number_4'
            ])
        # try to untag non-existing tag
        with raises(ValueError):
            img.untag('whalesnake_test_i_dont_exist')
        # try to untag the initial tag, again
        with raises(ws.WhalesnakeError):
            img.untag()
        #assert img.initial_name == ''
        # try to untag the initial tag, although was instantiated with id
        img2 = ws.Image(img.long_id)
        #assert img2.initial_name == ''
        with raises(ws.WhalesnakeError):
            img2.untag()
            
        img2 = ws.Image('non_existing_image')
        with raises(ws.WhalesnakeError):
            img2.untag()
        



