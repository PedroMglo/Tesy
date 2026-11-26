# Subsequent VMA inspection on Btrfs

R01 stopped with exit 34 on the first expert after the loader returned. Its
stdout contains one read-only MAP and 72 MADV_DONTNEED calls. The combined
error saved neither an address nor a VMA key. A separate one-page witness on
the original authenticated FD shows stat 0:56 and maps 0:38, inode 40127919
in both. The historical comparison rejects even this valid original mapping.

Before another load, qualify a read-only MAP_SHARED witness at file offset zero,
without a dereference. Authenticate its FD against the original file's stat
and match its canonical pathname, inode and permissions in /proc/self/maps.
Use this VMA device/inode/path key for all segments of each expert, preserving
the offset from the loader's observed whole-file mapping. Keep the C283
independent per-name offset/size/type audit. Release the witness on every
exit. Collect its mapping only after the startup observer has been disarmed.

The model-free test uses a sparse file, unaligned tensor offsets above 4 GiB,
a valid contiguous split, a pathname containing spaces, a symlink alias and
negative controls for a different inode, device, path, write permission,
anonymous page, gap, displaced offset and wrong authority. Verify a direct
read-only mapping of an existing non-model Btrfs file when available. Inspect
the already qualified tiny GGUF with the rebuilt driver and exactly the R03
numerical/stop gate. No new 120B loading belongs to this fixture.
