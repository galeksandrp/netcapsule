#from selenium import webdriver
#from selenium.webdriver.common.proxy import *

from bottle import route, default_app, run, request, response, redirect

import requests
import logging
from redis import StrictRedis

import time
import sys
import os

from argparse import ArgumentParser


PYWB_HOST_PORT = os.environ.get('PYWB_HOST_PORT', 'netcapsule_pywb_1:8080')

LOCAL_REDIS_HOST = 'netcapsule_redis_1'

REDIS_HOST = os.environ.get('REDIS_HOST', LOCAL_REDIS_HOST)

my_ip = '127.0.0.1'

pywb_ip = None
start_url = None
start_ts = None

redis = None
local_redis = None
DEF_EXPIRE_TIME = 30
expire_time = DEF_EXPIRE_TIME

HOST = os.environ.get('HOSTNAME', 'localhost')


def set_timestamp(timestamp):
    params = {'ts': timestamp,
              'ip': my_ip}

    try:
        r = requests.get('http://set.pywb.proxy/', params=params, proxies={'http': PYWB_HOST_PORT, 'https': PYWB_HOST_PORT})

        if r.status_code == 200:
            return {'success': r.json()}
        else:
            return {'error': r.body}

    except Exception as e:
        return {'error': str(e)}


@route('/set')
def route_set_ts():
    ts = request.query.get('ts')
    res = set_timestamp(ts)
    return res


@route(['/ping'])
def ping():
    if not redis.hget('all_containers', HOST):
        return

    global expire_time
    expire_time = redis.get('container_expire_time')
    if not expire_time:
        expire_time = DEF_EXPIRE_TIME

    redis.expire('c:' + HOST, expire_time)

    ts = request.query.get('ts')

    base_key = my_ip + ':' + ts + ':'

    # all urls
    all_urls = local_redis.hgetall(base_key + 'urls')

    count = 0
    min_sec = sys.maxint
    max_sec = 0
    for url, sec in all_urls.iteritems():
        count += 1
        sec = int(sec)
        min_sec = min(sec, min_sec)
        max_sec = max(sec, max_sec)

    # all_hosts
    all_hosts = local_redis.smembers(base_key + 'hosts')

    referrer = local_redis.get(base_key + 'r')

    referrer_secs = int(all_urls.get(referrer, 0))

    return {'urls': count,
            'min_sec': min_sec,
            'max_sec': max_sec,
            'hosts': list(all_hosts),
            'referrer': referrer,
            'referrer_secs': referrer_secs
           }


@route('/')
def homepage():
    global start_url
    redirect(start_url, code=302)




PROXY_PAC = """
function FindProxyForURL(url, host)
{
    if (isInNet(host, "10.0.2.2") || shExpMatch(url, "http://10.0.2.2:6082/*")) {
        return "DIRECT";
    }

    return "PROXY %s:8080";
}
"""

@route('/proxy.pac')
def proxy():
    response.content_type = 'application/x-ns-proxy-autoconfig'
    return PROXY_PAC % pywb_ip


def do_init():
    logging.basicConfig(format='%(asctime)s: [%(levelname)s]: %(message)s',
                        level=logging.DEBUG)

    parser = ArgumentParser('netcapsule browser manager')
    parser.add_argument('--my-ip')
    parser.add_argument('--pywb-ip')
    parser.add_argument('--start-url')
    parser.add_argument('--start-ts')

    r = parser.parse_args()

    global my_ip
    my_ip = r.my_ip

    global pywb_ip
    pywb_ip = r.pywb_ip

    global start_url
    start_url = r.start_url
    if '://' not in start_url:
        start_url = 'http://' + start_url

    # not used here for now
    global start_ts
    start_ts = r.start_ts

    global redis
    redis = StrictRedis(REDIS_HOST)

    global local_redis
    if REDIS_HOST != LOCAL_REDIS_HOST:
        local_redis = StrictRedis(LOCAL_REDIS_HOST)
    else:
        local_redis = redis

    # set initial url
    base_key = my_ip + ':' + start_ts + ':'
    local_redis.set(base_key + 'r', start_url)

    return default_app()

application = do_init()

@application.hook('after_request')
def enable_cors():
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'PUT, GET, POST, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'


if __name__ == "__main__":
    run(host='0.0.0.0', port='6082')
