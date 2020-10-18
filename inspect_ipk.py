#!/usr/bin/env python3.8
import unix_ar
import tarfile

INFILE = 'org.jellyfin.webos_0.2.2_all.ipk'



ar_file = unix_ar.open(INFILE, 'r')


print(dir(ar_file))


debian_binary = ar_file.open('debian-binary')
deb_version = debian_binary.read()
print(ar_file.getinfo('debian-binary').__dict__)
print(repr(deb_version))


print('Control:')
control = ar_file.open('control.tar.gz')
control_tar = tarfile.open(fileobj=control)

for obj in control_tar.getmembers():
    print(obj.name, obj.pax_headers, obj.size, obj.uid, obj.uname, obj.gname, obj.gid, oct(obj.mode))
    x = control_tar.extractfile(obj)
    if x:
        print(x.read())

print('Data:')
data = ar_file.open('data.tar.gz')
data_tar = tarfile.open(fileobj=data)

for obj in data_tar.getmembers():
    print(obj.name, obj.pax_headers, obj.size, obj.uid, obj.gid, oct(obj.mode), obj.isdir())
