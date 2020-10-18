#!/usr/bin/env python3.8
import os
import json
import time

from tarfile import TarFile, TarInfo, DIRTYPE
from typing import Union, TypedDict, Optional, IO
from io import BytesIO

from unix_ar import ArFile, ArInfo
import click


DEB_VERSION = b"2.0\n"

CONTROL_TEMPLATE = """Package: {id}
Version: {version}
Section: misc
Priority: optional
Architecture: all
Installed-Size: {size}
Maintainer: N/A <nobody@example.com>
Description: This is a webOS application.
webOS-Package-Format-Version: 2
webOS-Packager-Version: x.y.x
"""
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
    appinfo_file = os.path.join(base_path, "appinfo.json")

    if not os.path.isfile(appinfo_file):
        raise ValueError

    with open(appinfo_file, "rt") as fh:
        return json.load(fh)


def gen_filename(appinfo: AppInfo) -> str:
    return f"{appinfo['id']}_{appinfo['version']}_all.ipk"


def gen_packageinfo(appinfo: AppInfo) -> bytes:
    packageinfo = {
        "app": appinfo["id"],
        "id": appinfo["id"],
        "loc_name": appinfo["title"],
        "vendor": appinfo["vendor"],
        "version": appinfo["version"],
    }
    data = json.dumps(packageinfo, indent=2) + "\n"

    return data.replace("\r\n", "\n").encode("utf-8")


def gen_control(appinfo: AppInfo, size: int) -> bytes:
    control = CONTROL_TEMPLATE.format(size=size, **appinfo)
    return control.replace("\r\n", "\n").encode("utf-8")


def calc_size(base_path: str) -> int:
    size = 0
    for base, dirs, files in os.walk(base_path):
        for d in dirs:
            size += DIRECTORY_SIZE

        for f in files:
            filepath = os.path.join(base, f)
            filesize = os.stat(filepath).st_size
            size += filesize
    return size


FileData = Union[str, bytes, IO[bytes]]


def ar_addfile(ar: ArFile, name: str, data: FileData, size: Optional[int] = None):
    if isinstance(data, str):
        data = data.encode("utf-8")

    if isinstance(data, bytes):
        if size is None:
            size = len(data)
        data = BytesIO(data)

    if size is None and data.seekable():
        data.seek(0, os.SEEK_END)
        size = data.tell()

    if size is None:
        raise ValueError("Unable to determine size, and no size provided.")

    info = ArInfo(name)
    info.size = size
    info.mtime = int(time.time())
    info.perms = 0o666
    info.uid = 0
    info.gid = 0

    if data.seekable():
        data.seek(0)

    ar.addfile(info, data)


def tar_addfile(tar: TarFile, name: str, data: FileData, size: Optional[int] = None):
    if isinstance(data, str):
        data = data.encode("utf-8")

    if isinstance(data, bytes):
        if size is None:
            size = len(data)
        data = BytesIO(data)

    if size is None and data.seekable():
        data.seek(0, os.SEEK_END)
        size = data.tell()

    if size is None:
        raise ValueError("Unable to determine size, and no size provided.")

    name = name.replace(os.path.sep, "/")

    members = tar.getnames()
    dir_elements = name.split("/")[:-1]
    if dir_elements:
        for n in range(1, len(dir_elements) + 1):
            dirpath = "/".join(dir_elements[:n])
            if dirpath not in members:
                dir_info = TarInfo(dirpath)
                dir_info.mtime = int(time.time())
                dir_info.mode = 0o777
                dir_info.uid = 1000
                dir_info.gid = 1000
                dir_info.type = DIRTYPE

                tar.addfile(dir_info)

    info = TarInfo(name)
    info.size = size
    info.mtime = int(time.time())
    info.mode = 0o666
    info.uid = 1000
    info.gid = 1000

    if data.seekable():
        data.seek(0)

    tar.addfile(info, data)


def build(base_path: str, output: str):
    appinfo = get_appinfo(base_path)
    size = calc_size(base_path)
    size += 4 * DIRECTORY_SIZE  # usr/palm/applications/{appinfo['id']}/

    packageinfo_data = gen_packageinfo(appinfo)

    size += 2 * DIRECTORY_SIZE  # usr/palm/./packages/{appinfo['id']}/
    size += len(packageinfo_data)  # usr/palm/packages/{appinfo['id']}/packageinfo.json

    ar = ArFile(open(output, "wb"), "w")

    ar_addfile(ar, "debian-binary", DEB_VERSION)

    with BytesIO() as controlfh:
        with TarFile.open(mode="w:gz", fileobj=controlfh) as control_tarfh:
            control_data = gen_control(appinfo, size)
            tar_addfile(control_tarfh, "control", control_data)

        ar_addfile(ar, "control.tar.gz", controlfh)

    with BytesIO() as datafh:
        with TarFile.open(mode="w:gz", fileobj=datafh) as data_tarfh:
            output_base = f"usr/palm/applications/{appinfo['id']}"

            for base, dirs, files in os.walk(base_path):
                rel_base = os.path.relpath(base, base_path)

                for file_name in files:
                    input_file = os.path.join(base, file_name)

                    rel_file = os.path.relpath(input_file, base_path)
                    archive_path = os.path.join(output_base, rel_file)

                    with open(input_file, "rb") as fh:
                        tar_addfile(data_tarfh, archive_path, fh)

            packageinfo_name = f"usr/palm/packages/{appinfo['id']}/packageinfo.json"
            packageinfo_data = gen_packageinfo(appinfo)
            tar_addfile(data_tarfh, packageinfo_name, packageinfo_data)

        ar_addfile(ar, "data.tar.gz", datafh)


@click.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=True, file_okay=False))
@click.option("--output", type=click.Path(dir_okay=True, file_okay=True), default=None)
def cli(path: str, output: Optional[str] = None):
    appinfo = get_appinfo(path)

    if output is None:
        output_file = gen_filename(appinfo)
    elif os.path.isdir(output):
        output_file = os.path.join(output, gen_filename(appinfo))
    else:
        output_file = output

    build(path, output=output_file)
    click.echo(output_file)


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
