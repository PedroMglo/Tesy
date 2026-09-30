#ifndef _WIN32
#include <unistd.h>
#endif
// No replacement: incomplete/cancelled artefacts retain .partial, never a final name.
static FILE * c156_open_output(const char * final) {
    if (std::filesystem::exists(final)) return nullptr;
    return std::fopen((std::string(final)+".partial").c_str(),"wx");
}
static bool c156_finish_output(FILE * out,const char * final,bool accepted) {
    if (!out) return false;
    bool ok=!std::ferror(out);
    if(std::fflush(out))ok=false;
#ifndef _WIN32
    if(ok&&::fsync(fileno(out)))ok=false;
#endif
    if(std::fclose(out))ok=false;
    if(!accepted||!ok)return false;
    std::error_code error;
    const std::string temporary=std::string(final)+".partial";
    std::filesystem::create_hard_link(temporary,final,error); // atomic, fails if final exists
    if(error)return false;
    std::filesystem::remove(temporary,error);
    return !error;
}
