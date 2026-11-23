// Real GGML CPU graph/team barrier; only ith0 waits, all eight threads compute output.
#include "ggml.h"
#include "ggml-cpu.h"
#include <atomic>
#include <fstream>
#include <string>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <sys/resource.h>
struct State {int us;std::atomic<unsigned> mask{0};std::atomic<bool> bad{false};};
static double mono(){timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+1e-9*t.tv_nsec;}
static double cpu(){rusage r;getrusage(RUSAGE_SELF,&r);return r.ru_utime.tv_sec+r.ru_stime.tv_sec+1e-6*(r.ru_utime.tv_usec+r.ru_stime.tv_usec);}
static void op(ggml_tensor*d,const ggml_tensor*a,int ith,int nth,void*u){auto*s=(State*)u;s->mask.fetch_or(1u<<ith);if(nth!=8)s->bad=true;
 if(ith==0&&s->us){timespec t{0,s->us*1000L};while(nanosleep(&t,&t)&&errno==EINTR){}}
 float*x=(float*)a->data,*y=(float*)d->data;for(int i=ith;i<4096;i+=nth)y[i]=x[i]*2.0f+1.0f;}
int main(int argc,char**argv){if(argc!=2)return 2;State state;state.us=atoi(argv[1]);
 std::ifstream maps("/proc/self/maps");std::string line;while(std::getline(maps,line))if(line.find("libggml")!=std::string::npos||line.find("libgomp")!=std::string::npos)fprintf(stderr,"%s\n",line.c_str());fprintf(stderr,"GOMP_SPINCOUNT=%s\n",getenv("GOMP_SPINCOUNT")?getenv("GOMP_SPINCOUNT"):"UNSET");
 ggml_init_params p{4*1024*1024,nullptr,false};auto*c=ggml_init(p);auto*a=ggml_new_tensor_1d(c,GGML_TYPE_F32,4096);
 for(int i=0;i<4096;i++)((float*)a->data)[i]=(float)i;auto*d=ggml_map_custom1(c,a,op,GGML_N_TASKS_MAX,&state);ggml_set_output(d);
 auto*g=ggml_new_graph(c);ggml_build_forward_expand(g,d);double m=mono(),s=cpu();
 for(int i=0;i<64;i++)if(ggml_graph_compute_with_ctx(c,g,8)!=GGML_STATUS_SUCCESS)return 3;
 double wall=mono()-m,used=cpu()-s;bool eq=true;for(int i=0;i<4096;i++)eq&=((float*)d->data)[i]==2.0f*i+1.0f;
 printf("{\"delay_us\":%d,\"repetitions\":64,\"wall_s\":%.9f,\"cpu_s\":%.9f,\"thread_mask\":%u,\"valid\":%s}\n",state.us,wall,used,state.mask.load(),(eq&&!state.bad&&state.mask==255)?"true":"false");ggml_free(c);return eq&&!state.bad&&state.mask==255?0:4;}
