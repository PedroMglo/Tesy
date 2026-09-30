"""Read-only GGUF cache census; never touches mapped model bytes."""
import ctypes
import json
import os
from pathlib import Path

def census(path, *, relinquish=False):
    path=Path(path).resolve();stat=path.stat();mapped=[];unreadable=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            lines=(proc/'maps').read_text().splitlines()
        except PermissionError:
            unreadable.append(int(proc.name));continue
        except (FileNotFoundError,ProcessLookupError):continue
        for line in lines:
            fields=line.split(None,5)
            if len(fields)==6 and int(fields[4])==stat.st_ino and fields[5].removesuffix(' (deleted)')==str(path):
                mapped.append({'pid':int(proc.name),'line':line})
    if relinquish and mapped:raise RuntimeError('GGUF has active mappings; relinquish refused')
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC)
    lib=ctypes.CDLL(None,use_errno=True)
    lib.mmap.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_long]
    lib.mmap.restype=ctypes.c_void_p
    lib.mincore.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p]
    lib.munmap.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
    page=os.sysconf('SC_PAGE_SIZE');block=256*2**20
    count=resident=0;chunks=[]
    try:
        if relinquish:os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED)
        for offset in range(0,stat.st_size,block):
            size=min(block,stat.st_size-offset);n=(size+page-1)//page
            vector=(ctypes.c_ubyte*n)()
            addr=lib.mmap(None,size,1,2,fd,offset)
            if addr is None or addr==ctypes.c_void_p(-1).value:raise OSError(ctypes.get_errno(),'mmap census')
            try:
                if lib.mincore(addr,size,vector):raise OSError(ctypes.get_errno(),'mincore census')
                hot=sum(bool(x&1) for x in vector);resident+=hot;count+=n
                chunks.append({'offset':offset,'size':size,'pages':n,'resident_pages':hot})
            finally:lib.munmap(addr,size)
    finally:os.close(fd)
    return {'schema':'c147-mincore-v1','path':str(path),'dev':stat.st_dev,'inode':stat.st_ino,
            'size':stat.st_size,'page_size':page,'pages':count,'resident_pages':resident,
            'resident_upper_bound_bytes':resident*page,'census_metadata_peak_bytes':block//page,
            'relinquished_clean_pages':relinquish,'active_mappings':mapped,'unreadable_process_maps':unreadable,
            'equal_memory_status':'INCONCLUSIVE_UNREADABLE_MAPPING_OR_RESIDUAL' if unreadable or resident else 'NO_RESIDENT_PAGES_OBSERVED',
            'chunks':chunks,'limits':'mincore is residency, not per-page memcg ownership; kernel may change pages concurrently'}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('model',type=Path);p.add_argument('--relinquish',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with a.output.open('x') as f:json.dump(census(a.model,relinquish=a.relinquish),f,indent=2);f.write('\n')
