#pragma once

#include "../bounded_input.hpp"
#include "../../../../../cpu_numeric/vma/inspect.hpp"
#include "llama-mmap.h"
#include <charconv>
#include <cstdlib>
#include <memory>
#include <string_view>

namespace tesy {

class NativeInput {
public:
    NativeInput(const char *mode, const llama_model &model, ggml_backend_t backend)
        : file_(required("TESY_IK_BANK_MODEL"),"rb"), backend_(backend),
          source_(select(mode)), capacity_(capacity()), trace_(tracing()) {
        struct stat id{};
        if (std::string_view(ggml_backend_name(backend))!="CUDA0" || model.mappings.size()!=1 ||
            model.mappings.front()->is_anonymous() || fstat(file_.file_id(),&id) ||
            file_.size()!=model.mappings.front()->size())
            throw std::runtime_error("selective input requires a single original CUDA0 model mapping");
        witness_=ik_vma::Inspect::capture(file_.get_path().c_str(),id);
        base_=uintptr_t(model.mappings.front()->addr());
        bytes_=model.mappings.front()->size();
        std::fprintf(stderr,"TESY_NATIVE_INPUT %s %zu %d\n",mode,capacity_,int(trace_));
    }
    uint64_t bind(const ggml_tensor *w) const {
        if (!w || !w->data || !w->buffer || w->type!=GGML_TYPE_MXFP4 || !w->nb[2] ||
            !ggml_backend_buffer_is_host(w->buffer)) throw std::runtime_error("non-mapped expert");
        return witness_.offset(w->name,base_,bytes_,uintptr_t(w->data),ggml_nbytes(w));
    }
    void ids(ggml_backend_t backend,int layer,const int32_t *values,size_t count) {
        if (backend!=backend_ || !values || !count) throw std::runtime_error("bank ID stream");
        if (!reader_) {
            reader_=std::make_unique<BoundedBankInput>(file_.file_id(),capacity_,source_,
                         [backend]{ggml_backend_synchronize(backend);});
        }
        reader_->synchronize_ids();
        ++sites_;
        layer_=layer;
        if (trace_) {
            std::fprintf(stderr,"TESY_NATIVE_IDS %zu %d",sites_,layer);
            for (size_t i=0;i<count;++i) std::fprintf(stderr," %d",values[i]);
            std::fputc('\n',stderr);
        }
    }
    void send(int layer, const ggml_tensor *w, uint64_t start, size_t source_off,
              ggml_tensor *bank, size_t dest, size_t n) {
        if (!reader_ || layer!=layer_ || source_off>ggml_nbytes(w) || n>ggml_nbytes(w)-source_off ||
            dest>ggml_nbytes(bank) || n>ggml_nbytes(bank)-dest || start>bytes_ ||
            source_off>bytes_-start || n>bytes_-start-source_off)
            throw std::out_of_range("invalid native bank range");
        const auto file=start+source_off;
        const auto *mapped=static_cast<const char *>(w->data)+source_off;
        reader_->send(file,mapped,n,[&](const void *src,size_t len){
            if (trace_) std::fprintf(stderr,
                "TESY_NATIVE_SET %zu %d %s %s %" PRIu64 " %zu %zu %" PRIuPTR " %" PRIuPTR " %zu\n",
                sites_,layer,w->name,bank->name,file,dest,len,uintptr_t(mapped),uintptr_t(src),
                reader_->extra_drains());
            ggml_backend_tensor_set_async(backend_,bank,src,dest,len);
        });
        ++sets_;
        payload_+=n;
    }
    ~NativeInput() {
        const auto drains=reader_ ? reader_->extra_drains() : 0;
        reader_.reset(); // all bank buffers and the actual stream still belong to the live cache
        std::fprintf(stderr,"TESY_NATIVE_END %zu %zu %zu %zu\n",sites_,sets_,payload_,drains);
    }

private:
    static const char *required(const char *key) {
        const char *value=std::getenv(key);
        if (!value || !*value) throw std::invalid_argument(key);
        return value;
    }
    static Source select(std::string_view mode) {
        if (mode=="DIRECT") return Source::mapped;
        if (mode=="PREAD_RANDOM") return Source::ranges;
        throw std::invalid_argument("invalid TESY_IK_BANK_INPUT");
    }
    static size_t capacity() {
        std::string_view v=required("TESY_IK_BANK_CAPACITY");
        size_t n=0;
        const auto r=std::from_chars(v.data(),v.data()+v.size(),n);
        if (r.ec!=std::errc{} || r.ptr!=v.data()+v.size() || !n || n%BankInput::page)
            throw std::invalid_argument("invalid TESY_IK_BANK_CAPACITY");
        return n;
    }
    static bool tracing() {
        const char *raw=std::getenv("TESY_IK_BANK_TRACE");
        if (!raw || std::string_view(raw)=="0") return false;
        if (std::string_view(raw)=="1") return true;
        throw std::invalid_argument("invalid TESY_IK_BANK_TRACE");
    }

    llama_file file_;
    ggml_backend_t backend_;
    Source source_;
    size_t capacity_;
    bool trace_;
    ik_vma::Inspect witness_;
    uintptr_t base_{};
    size_t bytes_{},sites_{},sets_{},payload_{};
    int layer_=-1;
    std::unique_ptr<BoundedBankInput> reader_;
};
} // namespace tesy
