#!/usr/bin/env python3
"""Write deterministic synthetic Harmony prompts for fixed-token teacher forcing."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "workloads/c2_numeric_cases_v1.tsv"


def line(name, question, facts, continuation):
    prompt = "<|start|>user<|message|>" + question + " " + " ".join(facts) + "<|end|><|start|>assistant<|channel|>final<|message|>"
    if any("\t" in value or "\n" in value for value in (name, prompt, continuation)):
        raise ValueError("TSV delimiter in case")
    return "\t".join((name, prompt, continuation))


def main():
    cases = [
        line("quant_short", "Compute the sum of the numbered values, then explain the check.",
             [f"Entry {i:02d} has value {i*3+2};" for i in range(1, 12)],
             "The values form a simple arithmetic sequence. I will add each entry carefully and verify the total by pairing the first and last terms."),
        line("log_medium", "Audit the synthetic event stream. A later success resolves an earlier retry for the same operation.",
             [f"At minute {i:02d}, operation job{i%7} emitted {'SUCCESS' if i%5==0 else 'RETRY' if i%3==0 else 'FAIL'} with shard {i%4} and checksum tag c{i:02d};" for i in range(1, 9)],
             "I will group the events by operation identifier before deciding whether a final success exists. The checksum tags only distinguish lines and do not alter the success rule. I will count each operation once and then list the unresolved ones."),
        line("spec_pressure", "Apply the rules in order and summarize the effective configuration for the synthetic services.",
             [f"Rule {i:02d}: service svc{i%9} requests retention {7+i%6} days, region r{i%3}, priority {i%5}, and audit flag {'on' if i%2 else 'off'};" for i in range(1, 16)],
             "I will process the rules in their listed order and keep the latest applicable setting for each service. The region and audit flag must stay associated with the same service identifier. I will verify the final table against the last occurrence of each identifier before answering."),
    ]
    with OUTPUT.open("x") as target:
        target.write("\n".join(cases) + "\n")
    print(OUTPUT)


if __name__ == "__main__":
    main()
