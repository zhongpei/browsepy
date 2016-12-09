#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import logging
import os
import os.path
import json
import base64
import io
import gzip
import time

from flask import Flask, request, render_template, redirect, send_file, \
                  url_for, send_from_directory, stream_with_context, \
                  make_response, current_app
from werkzeug.exceptions import NotFound

from .__meta__ import __app__, __version__, __license__, __author__  # noqa
from .file import Node, OutsideRemovableBase, OutsideDirectoryBase, \
                  secure_filename
from .cache import cachedview
from . import compat
from . import manager

__basedir__ = os.path.abspath(os.path.dirname(compat.fsdecode(__file__)))

logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    static_url_path='/static',
    static_folder=os.path.join(__basedir__, 'static'),
    template_folder=os.path.join(__basedir__, 'templates')
    )
app.config.update(
    directory_base=compat.getcwd(),
    directory_start=compat.getcwd(),
    directory_remove=None,
    directory_upload=None,
    directory_tar_buffsize=262144,
    directory_downloadable=True,
    use_binary_multiples=True,
    plugin_modules=[],
    plugin_namespaces=(
        'browsepy.plugin',
        'browsepy_',
        '',
        ),
    disk_cache_enable=True,
    cache_class='browsepy.cache:SimpleLRUCache',
    cache_kwargs={'maxsize': 32},
    cache_browse_key='view/browse<{sort}>/{path}',
    browse_sort_properties=['text', 'type', 'modified', 'size']
    )
app.jinja_env.add_extension('browsepy.extensions.HTMLCompress')
app.jinja_env.add_extension('browsepy.extensions.JSONCompress')

if "BROWSEPY_SETTINGS" in os.environ:
    app.config.from_envvar("BROWSEPY_SETTINGS")

plugin_manager = manager.PluginManager(app)


def iter_cookie_browse_sorting():
    '''
    Get sorting-cookie data of current request.

    :yields: tuple of path and sorting property
    :ytype: 2-tuple of strings
    '''
    try:
        data = request.cookies.get('browse-sorting', 'e30=').encode('ascii')
        valid = current_app.config.get('browse_sort_properties', ())
        for path, prop in json.loads(base64.b64decode(data).decode('utf-8')):
            if prop.startswith('-'):
                if prop[1:] in valid:
                    yield path, prop
            elif prop in valid:
                yield path, prop
    except (ValueError, TypeError, KeyError) as e:
        logger.exception(e)


def get_cookie_browse_sorting(path, default):
    '''
    Get sorting-cookie data for path of current request.

    :returns: sorting property
    :rtype: string
    '''
    for cpath, cprop in iter_cookie_browse_sorting():
        if path == cpath:
            return cprop
    return default


def browse_sortkey_reverse(prop):
    '''
    Get sorting function for browse

    :returns: tuple with sorting gunction and reverse bool
    :rtype: tuple of a dict and a bool
    '''
    if prop.startswith('-'):
        prop = prop[1:]
        reverse = True
    else:
        reverse = False

    if prop == 'text':
        return (
            lambda x: (
                x.is_directory == reverse,
                x.link.text.lower() if x.link and x.link.text else x.name
                ),
            reverse
            )
    if prop == 'size':
        return (
            lambda x: (
                x.is_directory == reverse,
                x.stats.st_size
                ),
            reverse
            )
    return (
        lambda x: (
            x.is_directory == reverse,
            getattr(x, prop, None)
            ),
        reverse
        )


def cache_template_stream(key, stream):
    '''
    Yield and cache jinja template stream.

    :param key: cache key
    :type key: str
    :param stream: jinja template stream
    :type stream: iterable
    :yields: rendered jinja template chunks
    :ytype: str
    '''
    ts = time.time()
    buffer = io.BytesIO()
    with gzip.GzipFile(mode='wb', fileobj=buffer) as f:
        for part in stream:
            yield part
            f.write(part.encode('utf-8'))
    cache = current_app.extensions['plugin_manager'].cache
    cache.set(key, (buffer.getvalue(), request.url_root, ts))


def stream_template(template_name, **context):
    '''
    Some templates can be huge, this function returns an streaming response,
    sending the content in chunks and preventing from timeout.

    :param template_name: template
    :param **context: parameters for templates.
    :yields: HTML strings
    '''
    cache_key = context.pop('cache_key', None)
    app.update_template_context(context)
    stream = app.jinja_env.get_template(template_name).generate(context)
    if cache_key:
        stream = cache_template_stream(cache_key, stream)
    return current_app.response_class(stream_with_context(stream))


def get_cached_response(key, cancel_key=None):
    '''
    Get cached response object from key.

    :param key: cache key
    :type key: str
    :return: response object
    :rtype: flask.Response
    '''
    cache = current_app.extensions['plugin_manager'].cache
    cached, mints = cache.get_many(
        key,
        cancel_key or 'meta/cancel/{}'.format(key)
        )
    if not cached:
        return
    data, url_root, ts = cached
    if data and url_root < request.url_root and (ts is None or ts > mints):
        if 'gzip' in request.headers.get('Accept-Encoding', '').lower():
            response = current_app.response_class(data)
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Vary'] = 'Accept-Encoding'
            response.headers['Content-Length'] = len(data)
            return response
        return send_file(
            gzip.GzipFile(mode='rb', fileobj=io.BytesIO(data)),
            mimetype='text/html',
            as_attachment=False
            )


@app.context_processor
def template_globals():
    return {
        'manager': app.extensions['plugin_manager'],
        'len': len,
        }


@app.route('/app/browserconfig.xml', endpoint='msapplication-config')
@cachedview
def msapplication_config():
    return render_template('msapplication-config.xml')


@app.route('/app/manifest.json', endpoint='android-manifest')
@cachedview
def android_manifest():
    return render_template('android-manifest.json')


@app.route('/sort/<string:property>', defaults={"path": ""})
@app.route('/sort/<string:property>/<path:path>')
def sort(property, path):
    try:
        directory = Node.from_urlpath(path)
    except OutsideDirectoryBase:
        return NotFound()

    if not directory.is_directory:
        return NotFound()

    data = [
        (cpath, cprop)
        for cpath, cprop in iter_cookie_browse_sorting()
        if cpath != path
        ]
    data.append((path, property))
    raw_data = base64.b64encode(json.dumps(data).encode('utf-8'))

    # prevent cookie becoming too large
    while len(raw_data) > 3975:  # 4000 - len('browse-sorting=""; Path=/')
        data.pop(0)
        raw_data = base64.b64encode(json.dumps(data).encode('utf-8'))

    response = redirect(url_for(".browse", path=directory.urlpath))
    response.set_cookie('browse-sorting', raw_data)
    return response


@app.route("/browse", defaults={"path": ""})
@app.route('/browse/<path:path>')
def browse(path):
    sort_property = get_cookie_browse_sorting(path, 'text')

    if current_app.config['disk_cache_enable']:
        cache_key = current_app.config.get('cache_browse_key', '').format(
            sort=sort_property,
            path=path
            )
        cached_response = get_cached_response(cache_key)
        if cached_response:
            return cached_response
    else:
        cache_key = None  # disables response cache

    sort_fnc, sort_reverse = browse_sortkey_reverse(sort_property)

    try:
        directory = Node.from_urlpath(path)
        if directory.is_directory:
            return stream_template(
                'browse.html',
                cache_key=cache_key,
                file=directory,
                sort_property=sort_property,
                sort_fnc=sort_fnc,
                sort_reverse=sort_reverse
                )
    except OutsideDirectoryBase:
        pass
    return NotFound()


@app.route('/open/<path:path>', endpoint="open")
def open_file(path):
    try:
        file = Node.from_urlpath(path)
        if file.is_file:
            return send_from_directory(file.parent.path, file.name)
    except OutsideDirectoryBase:
        pass
    return NotFound()


@app.route("/download/file/<path:path>")
def download_file(path):
    try:
        file = Node.from_urlpath(path)
        if file.is_file:
            return file.download()
    except OutsideDirectoryBase:
        pass
    return NotFound()


@app.route("/download/directory/<path:path>.tgz")
def download_directory(path):
    try:
        directory = Node.from_urlpath(path)
        if directory.is_directory:
            return directory.download()
    except OutsideDirectoryBase:
        pass
    return NotFound()


@app.route("/remove/<path:path>", methods=("GET", "POST"))
def remove(path):
    try:
        file = Node.from_urlpath(path)
    except OutsideDirectoryBase:
        return NotFound()
    if request.method == 'GET':
        if not file.can_remove:
            return NotFound()
        return render_template('remove.html', file=file)
    parent = file.parent
    if parent is None:
        # base is not removable
        return NotFound()

    try:
        file.remove()
    except OutsideRemovableBase:
        return NotFound()

    return redirect(url_for(".browse", path=parent.urlpath))


@app.route("/upload", defaults={'path': ''}, methods=("POST",))
@app.route("/upload/<path:path>", methods=("POST",))
def upload(path):
    try:
        directory = Node.from_urlpath(path)
    except OutsideDirectoryBase:
        return NotFound()

    if not directory.is_directory or not directory.can_upload:
        return NotFound()

    for v in request.files.listvalues():
        for f in v:
            filename = secure_filename(f.filename)
            if filename:
                filename = directory.choose_filename(filename)
                filepath = os.path.join(directory.path, filename)
                f.save(filepath)
    return redirect(url_for(".browse", path=directory.urlpath))


@app.route("/")
def index():
    path = app.config["directory_start"] or app.config["directory_base"]
    try:
        urlpath = Node(path).urlpath
    except OutsideDirectoryBase:
        return NotFound()
    return browse(urlpath)


@app.after_request
def page_not_found(response):
    if response.status_code == 404:
        return make_response((render_template('404.html'), 404))
    return response


@app.errorhandler(404)
def page_not_found_error(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):  # pragma: no cover
    logger.exception(e)
    return getattr(e, 'message', 'Internal server error'), 500
