## RDNA3 RISCV based command processor

The AMD command processor in RNDA3 makes use of RISCV64 cores, one per micro
engine.

Just like it's predecessor there is fixed function hw  frontend to handle
fetching dwords from the command stream, either from main memory through the ROQ
or from (presumably) a fifo between PFP and ME.

Command frontend registers:

* tp+0x302 reads a dword from command stream
* tp+0x2c  also reads a dword from command stream
* tp+0 pushes into ME (PFP)
* tp+3 indirect command load?
* tp+0x5 look up `a0` in jmptbl (ME)
* tp+0x7 loop up `a0` in jmptbl (PFP)
* tp+0x98 add entry to jmptbl
* tp+7 decode jmptbl
* tp+13 memory operation status, != 1 when ready (used for CP_DMA and indirect commands)
* tp+0x38b remaining cnt? setting to 0 forwards to ME?

0x1200 interrupt
0x3200 reset vector

During initialization a jump table is loaded by writing dwords to `tp+0x98`.
Each dword represents a key value pair.

bits   description
00:19  handler address
20:28  opcode

Addresses map directly to offsets in the file despite the file containing some
headers. It appears like the firmware images map 1:1 to the processors memory.

This same format is used in the f32 based command processor found in RDNA3.5
GPUs.

Run `python jmptbl.py` for the PFP jump table, `python jmptbl.py me` for the ME
jump table.

Note that the jump tables are hardcoded in the script and need to be manually
copied from the firmware.

Individual packets are handled by functions which look like unreachable code.

After some initialization the following loop fetches and executes packets.

```
main_pkt_loop:
lwu        a0,0x302(tp) ; fetch next packet
ld         a5,0x7(tp)   ; get address of next packet with jmptbl
jalr       ra,a5,0x0    ; call the handler for the packet
j          main_pkt_loop
```

Reading 0x5(PFP) or 0x7(ME) decodes the header from `a0`. `a0` corresponds to
the first argument in the c calling convenction therefore it looks like calling
into that address with the packet header dwird as the first argument. From the
handler perspective it looks like being called with the header as the first
argument.

Commands either chain (jr) into the next command, chain into the main packet
loop, or just return.

In the PFP commands often forward the header plus remaining dwords into the ME.
A single dword can be passed to the ME by writing to `tp+0`, for example

```
sw         a0,0x0(tp)
```

pushes the packet header to the ME.

The following sequence:
```
sd         zero,0x0(s8)
sw         zero,0x38b(tp)
```

Pushes all remaining dwords of the current packet to the ME.

At times PFP pushes hardcoded commands into the ME. The `pkt3print.py` utility
found in this directory can be used to decode those packets by passing the hex
as a command line argument.

Besides the aforemention command frontend registers the CP has access to control
registers that are used to comunicate with the rest of the GPU.

### Example: compute dispatch registers

* s9+0x7fc block_x
* s9+0x7f8 block_y
* s9+0x7f4 block_z
* s9+0x800 dispatch initiator
* s9+0x608 writing 0 triggers dispatch?

## Indirect commands

PFP can execute the following sequence
```
ld         a3,0x1b(tp)      ; (or 0x1a)
lwu        a4,0x302(tp)     ; load low addr
lwu        a5,0x2c(tp)      ; load high addr
slli       a4,a4,0x20
srli       a4,a4,0x20
add        a4,a4,a3
sd         a4,0x3(tp)       ; lower address?
ori        a5,a5,0x3        ; tell it to load 3 dwords
slli       a5,a5,0x20
srli       a5,a5,0x20
sd         a5,0x3(tp)       ; (or 0x92) high address, len and start the load?
```

Which will load data from main memory and push it to the ME

ME needs to do the following before receiving the data

```
sw         zero,0x10(tp)        ; ?
lwu        a5,0x302(tp)         ; load packet from PFP normally
li         a5,0x1               ; (or 0x2)
sw         a5,0x16(tp)          ; tell ME to load from memory?
li         a4,0x1
LAB_00006c14
ld         a5,0x13(tp)          ; loop until 0x13 becomes 0 to wait for mem op
bne        a5,a4,LAB_00006c14
lwu        a5,0x302(tp)         ; this time we fetch from memory instead of cs
sw         zero,0x16(tp)        ; go back to fetching commands?
LAB_00006c38
ld         a5,0x13(tp)
bne        a5,zero,LAB_00006c38 ; ... which requires waiting as well?
```

The registers in parenthesis are used by draw indirect packets, the other
ones by dispatch indirect.
Perhaps two different channels are present to allow said commands to work in
parallel?
