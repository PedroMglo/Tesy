// Exercise the same controller used by the four native workers, without model data.
#include "cpu-weight-bank.h"
#include <iostream>
#include <numeric>
#include <sstream>
#include <string>

using Bank = CpuWeightBank;

static void expect(bool condition, const char *message) {
    if (!condition) throw std::runtime_error(message);
}

struct Model {
    Bank bank;
    std::array<int,Bank::primary> frames, experts;
    std::array<unsigned,Bank::primary> generations{};
    explicit Model(Bank::Mode mode) : bank(mode) {
        std::iota(frames.begin(), frames.end(), 0);
        experts.fill(-1);
    }
    Bank::Transfer reserve(int layer, int slot, int expert) {
        const int logical = layer * Bank::slots + slot;
        auto t = bank.reserve(layer, slot, expert, experts.at(logical), frames.at(logical));
        experts[logical] = expert;
        ++generations[logical];
        return t;
    }
    void publish(const Bank::Transfer &t) {
        expect(bank.eligible(t), "attempted to publish a blocked writer");
        bank.complete(t, Bank::key(t.logical / Bank::slots, experts[t.logical]), true);
    }
};

static void full_bank(Bank::Mode mode) {
    Model m(mode);
    for (int i = 0; i < Bank::capacity; ++i)
        m.publish(m.reserve(i / Bank::slots, i % Bank::slots, i % Bank::slots));
    const auto first = m.bank.acquire(m.frames[0], Bank::key(0,0));
    const auto second = m.bank.acquire(m.frames[0], Bank::key(0,0));
    for (int i = 0; i < Bank::capacity; ++i)
        m.publish(m.reserve(i / Bank::slots, i % Bank::slots, 40 + i % Bank::slots));
    expect(m.bank.occupied() == Bank::capacity, "expected full bank");
    const auto disputed = m.reserve(0,0,0);
    const bool reference = mode == Bank::Mode::reference;
    expect(!disputed.from_pack() && disputed.target == first.frame, "wrong promotion");
    expect(m.bank.eligible(disputed) == reference, "wrote a frame with two readers");
    expect(m.bank.release(first) && !m.bank.release(first), "duplicate release");
    auto forged = second;
    ++forged.epoch;
    expect(!m.bank.release(forged) && m.bank.eligible(disputed) == reference, "lost second reader");
    expect(m.bank.release(second), "last reader did not release");
    m.publish(disputed);
    expect(m.bank.drained() && m.bank.stats.staged_hits == (reference ? 0u : 1u),
           "saturated promotion did not drain");
}

static void pending_copy(bool cancel) {
    Model m(Bank::Mode::copy);
    m.publish(m.reserve(0,0,0));
    m.publish(m.reserve(0,1,1));
    m.publish(m.reserve(0,0,2));
    const auto copy = m.reserve(0,0,0);
    const auto later = m.reserve(0,1,3);
    expect(copy.out_of_place() && m.bank.eligible(copy) && copy.source == later.target &&
           !m.bank.eligible(later), "unprotected copy input");
    if (cancel) m.bank.cancel_queued(copy);
    else m.publish(copy);
    bool stale_rejected = false;
    try { m.bank.cancel_queued(copy); }
    catch (const std::logic_error &) { stale_rejected = true; }
    expect(stale_rejected, "stale cancellation");
    m.publish(later);
    expect(m.bank.drained(), "copy hold did not drain");
}

// Input is one complete primary snapshot, followed by committed reservations in accept order.
// No physical time is inferred from this serial replay.
static void replay(Bank::Mode mode) {
    Model m(mode);
    std::array<bool,Bank::primary> seen{};
    int initial = 0;
    int previous_index = -1;
    std::string line;
    while (std::getline(std::cin,line)) {
        std::istringstream row(line);
        char tag;
        int layer, slot, expert, old, index;
        unsigned generation;
        expect(bool(row >> tag), "empty replay row");
        if (tag == 'S') {
            expect(bool(row >> layer >> slot >> generation >> expert) && !m.bank.stats.reservations &&
                   layer >= 0 && layer < Bank::layers && slot >= 0 && slot < Bank::slots &&
                   expert >= -1 && expert < 128, "invalid snapshot row");
            const int logical = layer * Bank::slots + slot;
            expect(!seen[logical], "duplicate snapshot slot");
            seen[logical] = true;
            ++initial;
            m.experts[logical] = expert;
            m.generations[logical] = generation;
            if (expert >= 0) m.bank.initial_resident(m.frames[logical],Bank::key(layer,expert));
        } else {
            expect(tag == 'R' && bool(row >> index >> layer >> slot >> generation >> expert >> old) &&
                   initial == Bank::primary && index > previous_index &&
                   layer >= 0 && layer < Bank::layers && slot >= 0 && slot < Bank::slots,
                   "invalid reservation");
            previous_index = index;
            const int logical = layer * Bank::slots + slot;
            expect(m.experts[logical] == old && m.generations[logical] + 1 == generation,
                   "primary generation or victim mismatch");
            const auto captures = m.bank.stats.captures;
            const auto staged = m.bank.stats.staged_hits;
            auto t = m.reserve(layer,slot,expert);
            m.publish(t);
            std::cout << index << ' ' << !t.from_pack() << ' ' << m.bank.stats.captures - captures
                      << ' ' << t.source << ' ' << t.target << ' ' << m.bank.stats.staged_hits - staged
                      << ' ' << m.bank.occupied() << '\n';
        }
        std::string tail;
        expect(!(row >> tail), "extra replay fields");
    }
    expect(previous_index >= 0 && m.bank.drained(), "incomplete replay");
}

int main(int argc, char **argv) {
    try {
        if (argc == 1) {
            full_bank(Bank::Mode::copy);
            full_bank(Bank::Mode::reference);
            pending_copy(false);
            pending_copy(true);
            std::cout << "saturation, two readers, source hold, cancel, stale ticket: PASS\n";
        } else {
            const std::string role = argv[1];
            expect(argc == 2 && (role == "--replay-id" || role == "--replay-copy"), "invalid mode");
            replay(role == "--replay-id" ? Bank::Mode::reference : Bank::Mode::copy);
        }
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
