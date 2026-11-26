#pragma once
#include "llama-moe-stream.h"

bool lease_prepare(const llama_moe_stream_work &);
void lease_wait(const llama_moe_stream_work &, std::unique_lock<std::mutex> &, bool);
void lease_install(const llama_moe_stream_work &);
void lease_end();
