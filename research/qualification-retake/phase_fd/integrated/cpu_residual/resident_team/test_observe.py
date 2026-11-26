"""Synthetic coverage/faults for the observer. No GGML forward or accelerator."""

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDENTITY = "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313"
HEADER = """
#pragma once
enum ggml_op { GGML_OP_NONE, GGML_OP_MUL_MAT_ID };
struct ggml_tensor { enum ggml_op op; };
"""
HARNESS = r"""
#include "observe.c"
#include <assert.h>
int main(int argc, char **argv) {
    assert(argc==2);
    image_ok=1;
    struct ggml_tensor nodes_local[NODES];
    const char *mode=argv[1];
    for (int i=0;i<NODES;i++) {
        nodes_local[i].op=GGML_OP_MUL_MAT_ID;
        assert(team_observe_add(&nodes_local[i],i/3,i%3)==0);
    }
    assert(team_observe_add(&nodes_local[0],0,0)<0);
    team_observe_begin(0);
    assert(team_observe_end()==0);
    team_observe_begin(1);
    for (int i=0;i<NODES;i++) for (int j=0;j<LANES;j++) {
        int lane[2]={j,LANES};
        if (i==0 && j==0 && strcmp(mode,"missing")==0) continue;
        if (i==0 && j==0 && strcmp(mode,"nthreads")==0) lane[1]=1;
        bool first=i==0 && j==0;
        enter_node(&nodes_local[i],lane,
                   first && strcmp(mode,"foreign")==0 ? 0x1234 : EXTRA_RETURN,
                   first && strcmp(mode,"extra")==0);
        if (!(first && strcmp(mode,"noinner")==0)) barrier_edge(INNER_A_RETURN);
        if (first && strcmp(mode,"twoinner")==0) barrier_edge(INNER_C_RETURN);
        barrier_edge(i==NODES-1 ? LAST_RETURN : BETWEEN_RETURN);
        if (first && strcmp(mode,"duplicate")==0) enter_node(&nodes_local[i],lane,EXTRA_RETURN,0);
    }
    int n=team_observe_end();
    if (strcmp(mode,"ok")!=0) return n<0 ? 0 : 1;
    assert(n==ROWS);
    for(int i=0;i<n;i++) {
        int w,r,ith,nth,tid,a,b; int64_t start,end;
        assert(team_observe_row(i,&w,&r,&ith,&nth,&tid,&a,&b,&start,&end)==0);
        assert(w==i/24 && r==(i/8)%3 && ith==i%8 && nth==8);
        assert(tid>0 && a>=0 && b>=0 && end>start && start>0);
    }
    assert(team_observe_end()<0);
    return 0;
}
"""


class ObserveTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "C compiler required for synthetic markers")
    def test_complete_rows_off_and_faults(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "ggml.h").write_text(HEADER)
            (out / "test.c").write_text(HARNESS)
            exe = out / "test"
            subprocess.run(
                [
                    "cc",
                    "-std=gnu11",
                    "-O2",
                    "-Wall",
                    "-Werror",
                    "-I",
                    out,
                    "-I",
                    HERE,
                    out / "test.c",
                    "-ldl",
                    "-pthread",
                    "-o",
                    exe,
                ],
                check=True,
            )
            for case in (
                "ok",
                "missing",
                "foreign",
                "extra",
                "noinner",
                "twoinner",
                "duplicate",
                "nthreads",
            ):
                with self.subTest(case=case):
                    subprocess.run([exe, case], check=True, timeout=3)

    @unittest.skipUnless(os.environ.get("TESY_TEAM_CPU_ELF"), "opt-in pinned ELF inspection")
    def test_pin_has_calls_at_observed_boundaries(self):
        image = Path(os.environ["TESY_TEAM_CPU_ELF"])
        self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), IDENTITY)
        lines = subprocess.check_output(
            ["objdump", "-dw", "--disassemble=ggml_graph_compute_thread.isra.0", image], text=True
        )
        found = {
            (int(pc, 16), name)
            for pc, name in re.findall(
                r"^\s*([0-9a-f]+):.*?\bcall\s+[0-9a-f]+ <(ggml_barrier|"
                r"ggml_cpu_extra_compute_forward)@plt>",
                lines,
                flags=re.MULTILINE,
            )
        }
        self.assertEqual(
            found,
            {(0x68E8, "ggml_cpu_extra_compute_forward")}
            | {(pc, "ggml_barrier") for pc in (0x688B, 0x692C, 0x7671, 0x7F2A, 0x7F4A)},
        )


if __name__ == "__main__":
    unittest.main()
