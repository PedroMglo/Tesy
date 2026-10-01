"""Generate the original C127 capture with only a fail-closed canonical direct reader."""
import argparse,hashlib,json
from pathlib import Path

def generate(out):
 source=Path(__file__).with_name('c127_slots40_boundary_capture.cpp').read_text()
 old='''void pread_exact(int fd, void * data, size_t size, size_t offset) {
    auto * p = static_cast<uint8_t *>(data);
    size_t done = 0;
    while (done < size) {
        const ssize_t n = pread(fd, p+done, size-done, offset+done);
        check(n > 0, "short/error read of canonical GGUF expert slice");
        done += static_cast<size_t>(n);
    }
}'''
 assert source.count(old)==1
 edits=[('#include "gguf.h"','#include "gguf.h"\n#include "c210_direct_reader.h"'),
 ('    int model_fd = -1;','    tesy_witness::direct_reader canonical_reader;'),
 (old,'void pread_exact(const tesy_witness::direct_reader & reader, void * data, size_t size, size_t offset) { reader.read(data,size,offset); }'),
 ('pread_exact(state.model_fd,','pread_exact(state.canonical_reader,'),
 ('    ggml_context * meta = nullptr;','    state.canonical_reader.open_file(model);\n    ggml_context * meta = nullptr;'),
 ('    check(gguf && meta, "cannot parse canonical GGUF metadata");','    check(gguf && meta && ggml_used_mem(meta) <= 64u*1024u*1024u && gguf_get_data_offset(gguf) <= 64u*1024u*1024u, "canonical metadata bound/parser failed");'),
 ('    state.model_fd = open(model,O_RDONLY|O_CLOEXEC);\n    check(state.model_fd >= 0, "cannot open canonical GGUF");','    for (const auto & layer : state.canonical) for (const auto & component : layer) state.canonical_reader.validate_range(component.offset, component.per_expert*expert_count);\n    std::cout << "CANONICAL_DIRECT mem_align=" << state.canonical_reader.memory_alignment() << " offset_align=" << state.canonical_reader.offset_alignment() << " fd=" << state.canonical_reader.descriptor() << " scratch_max=8388608 meta_max=67108864\\n" << std::flush;'),
 ('        close(state.model_fd);','        check(state.bytes + static_cast<size_t>(vocab)*sizeof(float)*5 + state.index.size() + state.masked.size() + state.checked.size() + state.route_prestate.size() <= 256u*1024u*1024u, "aggregate capture/logits/index bound exceeded");')]
 for a,b in edits:
  assert source.count(a)==1,(a,source.count(a));source=source.replace(a,b)
 # GGUF tensor offset overflow is checked before addition; logical source multiplication fixed128*slice.
 a='''            state.canonical[static_cast<size_t>(layer)][kind] = {
                gguf_get_data_offset(gguf) + gguf_get_tensor_offset(gguf,id),per};'''
 b='''            const size_t base = gguf_get_data_offset(gguf), relative = gguf_get_tensor_offset(gguf,id);
            check(relative <= std::numeric_limits<size_t>::max()-base, "canonical offset addition overflow");
            state.canonical[static_cast<size_t>(layer)][kind] = {base + relative,per};'''
 assert source.count(a)==1;source=source.replace(a,b)
 out.write_text(source)
 return {'original_sha256':hashlib.sha256(Path(__file__).with_name('c127_slots40_boundary_capture.cpp').read_bytes()).hexdigest(),'generated_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'changes':'Only observer canonical reader, bounds and receipt; backend/graph/callback coverage unchanged','reader_sha256':hashlib.sha256(Path(__file__).with_name('c210_direct_reader.h').read_bytes()).hexdigest()}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args();print(json.dumps(generate(a.out)))
