#!/usr/bin/env python3.8
import tarfile
import os
import json
import time

from typing import Dict, Union, TypedDict, Optional, IO, overload
from io import BytesIO

import unix_ar
import click
from unix_ar import ArFile


DEB_VERSION = b'2.0\n'

CONTROL_TEMPLATE = '''Package: {id}
Version: {version}
Section: misc
Priority: optional
Architecture: all
Installed-Size: {size}
Maintainer: N/A <nobody@example.com>
Description: This is a webOS application.
webOS-Package-Format-Version: 2
webOS-Packager-Version: x.y.x
'''
DIRECTORY_SIZE = 4096

class AppInfo(TypedDict):
    id: str
    type: str
    title: str
    appDescription: str
    icon: str
    main: str
    bgImage: str
    version: str
    splashBackground: str
    bgColor: str
    vendor: str
    largeIcon: str
    iconColor: str
    disableBackHistoryAPI: bool


def get_appinfo(base_path) -> AppInfo:
    appinfo_file = os.path.join(base_path, 'appinfo.json')

    if not os.path.isfile(appinfo_file):
        raise ValueError

    with open(appinfo_file, 'rt') as fh:
        return json.load(fh,)


def gen_filename(appinfo: AppInfo) -> str:
    return f"{appinfo['id']}_{appinfo['version']}_all.ipk"


def gen_packageinfo(appinfo: AppInfo) -> bytes:
    data = json.dumps({
        "app": appinfo['id'],
        "id": appinfo['id'],
        "loc_name": appinfo['title'],
        "vendor": appinfo['vendor'],
        "version": appinfo['version'],
    }, indent=2) + '\n'

    return data.replace('\r\n', '\n').encode('utf-8')


def gen_control(appinfo: AppInfo, size: int) -> bytes:
    control = CONTROL_TEMPLATE.format(size=size, **appinfo)
    return control.replace('\r\n', '\n').encode('utf-8')


def calc_size(base_path: str) -> int:
    size = 0
    for base, dirs, files in os.walk(base_path):
        for d in dirs:
            dirpath = os.path.join(base, d)
            print(dirpath + '/', DIRECTORY_SIZE)
            size += DIRECTORY_SIZE

        for f in files:
            filepath = os.path.join(base, f)
            filesize = os.stat(filepath).st_size
            print(filepath, filesize)
            size += filesize
    return size


def ar_addfile(ar: unix_ar.ArFile, name: str, data: Union[str, bytes, IO[bytes]], size: Optional[int] = None):
    if isinstance(data, str):
        data = data.encode('utf-8')

    if isinstance(data, bytes):
        if size is None:
            size = len(data)
        data = BytesIO(data)

    if size is None and data.seekable():
        data.seek(0, os.SEEK_END)
        size = data.tell()

    if size is None:
        raise ValueError('Unable to determine size, and no size provided.')

    info = unix_ar.ArInfo(name)
    info.size = size
    info.mtime = int(time.time())
    info.perms = 0o666
    info.uid = 0
    info.gid = 0

    if data.seekable():
        data.seek(0)

    ar.addfile(info, data)


def tar_addfile(tar: tarfile.TarFile, name: str, data: Union[str, bytes, IO[bytes]], size: Optional[int] = None):
    if isinstance(data, str):
        data = data.encode('utf-8')

    if isinstance(data, bytes):
        if size is None:
            size = len(data)
        data = BytesIO(data)

    if size is None and data.seekable():
        data.seek(0, os.SEEK_END)
        size = data.tell()

    if size is None:
        raise ValueError('Unable to determine size, and no size provided.')

    info = tarfile.TarInfo(name)
    info.size = size
    info.mtime = int(time.time())
    info.mode = 0o666
    info.uid = 0
    info.gid = 0

    if data.seekable():
        data.seek(0)

    # tar.getmembers  # Add directories if missing

    tar.addfile(info, data)


def build(base_path: str, output: str):
    appinfo = get_appinfo(base_path)
    size = calc_size(base_path)
    size += 4 * DIRECTORY_SIZE  # usr/palm/applications/{appinfo['id']}/

    print(size)
    packageinfo_data = gen_packageinfo(appinfo)
    print(repr(packageinfo_data))
    print(len(packageinfo_data))

    size += 2 * DIRECTORY_SIZE  # usr/palm/./packages/{appinfo['id']}/
    size += len(packageinfo_data)  # usr/palm/packages/{appinfo['id']}/packageinfo.json
    print(size)

    ar = unix_ar.open(output, 'w')

    ar_addfile(ar, 'debian-binary', DEB_VERSION)

    with BytesIO() as controlfh:
        with tarfile.open(mode='w:gz', fileobj=controlfh) as control_tarfh:
            control_data = gen_control(appinfo, size)
            tar_addfile(control_tarfh, 'control', control_data)

        ar_addfile(ar, 'control.tar.gz', controlfh)


    with BytesIO() as datafh:
        with tarfile.open(mode='w:gz', fileobj=datafh) as data_tarfh:
            output_base = f'usr/palm/applications/{appinfo["id"]}'

            packageinfo_name = f'usr/palm/packages/{appinfo["id"]}/packageinfo.json'
            packageinfo_data = gen_packageinfo(appinfo)
            tar_addfile(data_tarfh, packageinfo_name, packageinfo_data)

        ar_addfile(ar, 'data.tar.gz', datafh)


@click.command()
@click.argument('path', type=click.Path(exists=True, dir_okay=True, file_okay=False))
@click.option('--output', type=click.Path(dir_okay=True, file_okay=True), default=None)
def cli(path: str, output: Optional[str] = None):
    appinfo = get_appinfo(path)

    if output is None:
        output_file = gen_filename(appinfo)
    elif os.path.isdir(output):
        output_file = os.path.join(output, gen_filename(appinfo))
    else:
        output_file = output

    build(path, output=output_file)


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
