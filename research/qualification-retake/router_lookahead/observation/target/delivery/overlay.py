"""Apply the tile and packed-payload extension only to the pinned private build."""

from pathlib import Path


def change(text, old, new):
    if text.count(old) != 1:
        raise ValueError("changed C305 anchor: " + old[:70])
    return text.replace(old, new)


def apply(src: Path):
    store = src / "c291-expert-store.h"
    # Only the model-free executable uses reduced slab geometry.
    store.write_text(change(store.read_text(), "slab=4406400", "slab=4096"))
    stage = src / "c305-cpu-stage.h"
    s = change(
        stage.read_text(), '#include "c291-direct-reader.h"', '#include "c291-expert-store.h"'
    )
    s = change(s, "slab=4406400", "slab=tesy_expert_store::slab")
    needle = "    bool enabled=false;"
    s = change(
        s,
        needle,
        needle
        + """
    const tesy_expert_store *packed = nullptr;
    explicit c305_cpu_stage(const tesy_expert_store &store) : packed(&store) {
        const size_t align=4096;
        component_stride=slab;
        entry_stride=((slab*3+align-1)/align)*align;
        require(entry_stride*slots+sizeof(*this)<=arena_limit, "packed arena budget");
        void *p=nullptr;
        require(posix_memalign(&p,align,entry_stride*slots)==0,"packed arena allocation");
        arena.reset(static_cast<uint8_t*>(p));
        std::memset(p,0,entry_stride*slots);
    }
    void abandon(int i,uint64_t ticket) {
        auto &e=entries.at(i);
        if (e.status==EMPTY) return; // failed read already cleared its ticket
        require(e.ticket==ticket && e.demand && e.status!=CONSUMING,"foreign abandonment");
        e.demand=false;
        cancel(i);  // an outstanding positional read retains its buffer until complete()
    }""",
    )
    s = change(
        s,
        "call>=1&&call<=32&&layer>=2&&layer<=24",
        "call>=1&&call<=32&&layer>=(packed?1:2)&&layer<=24",
    )
    needle = 'require(e.status==READING&&e.ticket==ticket,"stage read owner stale");'
    s = change(
        s,
        needle,
        needle
        + """
        if (packed) {
            packed->read(e.layer,e.expert,component(i,0),fn);
            return;
        }""",
    )
    s = change(s, "if(arena)for(int k=", "if(arena&&!packed)for(int k=")
    stage.write_text(s)
    header = src / "llama-moe-stream.h"
    s = change(
        header.read_text(),
        "int64_t trace_route=0, trace_call=0;",
        "int64_t trace_route=0, trace_call=0; int stage_site=0;",
    )
    s = change(
        s,
        "    c294_window window;",
        """    c294_window window;
    int stage_site=0;
    void select_prefill_tile(int call,int tile) {
        std::lock_guard<std::mutex> lock(mtx);
        if (!((call==1 && tile==1) || (call==2 && tile>=1 && tile<=5))) {
            throw std::runtime_error("unsupported prefill call/tile");
        }
        const int next=(call-1)*5+tile;
        if (next<=stage_site) throw std::runtime_error("stale prefill tile");
        stage_site=next;
    }""",
    )
    header.write_text(
        change(
            s,
            "{sl,expert,slot,gen,active_route,owner}",
            "{sl,expert,slot,gen,active_route,owner,stage_site}",
        )
    )
    path = src / "llama-moe-stream.cpp"
    s = change(
        path.read_text(),
        "if(!sl||target<2||target>24)",
        "if(!sl||target<(prediction_stage->packed?1:2)||target>24||"
        "(prediction_stage->packed&&call!=stage_site))",
    )
    s = change(s, "||sl.il<2||", "||sl.il<(prediction_stage->packed?1:2)||")
    s = change(
        s,
        "staged=prediction_stage->find(int(w.trace_call),sl.il,w.expert);",
        "staged=prediction_stage->find(prediction_stage->packed ? w.stage_site : int(w.trace_call),"
        "sl.il,w.expert);",
    )
    s = change(
        s,
        "if(shutting_down||load_failed){sl.slot_claimed[w.slot]=0;cv_done.notify_all();break;}",
        """if(shutting_down||load_failed){
                        prediction_stage->abandon(staged,prediction_ticket);
                        if(w.gen==sl.slot_gen[w.slot]&&w.expert==sl.slot_expert[w.slot])
                            sl.slot_claimed[w.slot]=0;
                        cv_done.notify_all();break;
                    }""",
    )
    s = change(
        s,
        "load_failed=true;sl.slot_claimed[w.slot]=0;cv_done.notify_all();break;",
        """prediction_stage->abandon(staged,prediction_ticket);
                        if(w.gen==sl.slot_gen[w.slot]&&w.expert==sl.slot_expert[w.slot])
                            sl.slot_claimed[w.slot]=0;
                        load_failed=true;cv_done.notify_all();break;""",
    )
    s = change(s, "if(a->ne[1]!=1)", "if(!mgr->prediction_stage->packed && a->ne[1]!=1)")
    s = change(
        s,
        "mgr->prediction_router_locked(int(mgr->window.call.load()),*sl,ids,size_t(n));",
        "mgr->prediction_router_locked(mgr->prediction_stage->packed ? mgr->stage_site : "
        "int(mgr->window.call.load()),*sl,ids,size_t(n));",
    )
    needle = "    active_route=++window.next_route;sl.trace_route=active_route;"
    s = change(
        s,
        needle,
        """    if (prediction_stage && prediction_stage->packed && prediction_stage->enabled)
        prediction_router_locked(stage_site,sl,ids,n);
"""
        + needle,
    )
    path.write_text(s)
