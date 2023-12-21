import struct
from math import ceil
import zstandard as zstd
import sys

pkt3s = {}

with open("pkt3.txt") as f:
    for line in f:
        toks = line.split(' ')
        [pkt_name, opcode] = [toks[0], toks[-1]]
        opcode = int(opcode, 0)
        pkt3s[opcode] = pkt_name

def read_word(data):
    v = data[0]
    v += data[1] << 8
    v += data[2] << 16
    v += data[3] << 24
    return v

def print_val_hex(val):
    print(f"{val:08x}", end='')

def s16(d):
    return d - 0x10000 if d >= 0x8000 else d

def loc(off):
    return labels.get(off, "0x%x"%off)

lastadd = None

labels = {}
def addlabel(off):
    global labels
    if off not in labels:
        labels[off] = True

def dis(off, inst):
    global lastadd
    # .... .... .... .... .... .... .... ....
    #        ss ssdd dd
    rs = (inst >> 22) & 0xf
    rd = (inst >> 18) & 0xf
    rx = (inst >> 14) & 0xf

    imm = inst & 0xffff
    a = (inst >> 26)
    b = (inst >> 16) & 0x3
    tgt = ["", "reg", "mem", "unk"][b]
    c = inst & 0x3fff

    opc_r = opc_i = [
        # 32-bit instructions
        None, "add", "sub", None,
        "lsl", "lsr", None, None,
        None, "and", "orr", "eor",
        # Set to 1 if cond is true
        "seteq", "setne", "setgt", "setge",

        # Multiply (16x16 bit?)
        "mul",

        # Double (64-bit) versions
        "addd", "subd", None,
        "lsld", "lsrd", None, None,
        None, "andd", "orrd", "eord",
        "seteqd", "setned", "setgtd", "setged",
    ]
    if a == 0:
        return "nop"
    elif a == 0x1f:
        # Register-register instructions
        if c == 1 and rd == 0:
            # Register-register move (actually add with r0 which is always 0)
            return "mov r%d, r%d" % (rx, rs)
        if c < len(opc_r) and opc_r[c] is not None:
            return "%s r%d, r%d, r%d" % (opc_r[c], rx, rs, rd)
        else:
            return "  dw 0x%x  #rs=%d rd=%d rx=%d a=0x%x c=0x%x" % (inst, rs, rd, rx, a, c)
    elif (a,b) == (0x6,0):
        # Logical shift right and AND
        return "lsra r%d, r%d, #%d, #0x%x" % (rd, rs, imm&0x1f, imm>>5)
    elif (a,b) == (0x7,0):
        # AND with mask (all-1 bits surrounding shifted imm)
        val = (0xffffffff ^ ((0x7ff ^ (imm>>5)) << (imm&0x1f))) & 0xffffffff
        return "and r%d, r%d, #0x%x" % (rd, rs, val)
    elif (a,b) == (0x8,0):
        # OR with shifted imm
        if rs == 0:
            return "mov r%d, #0x%x" % (rd, (imm>>5) << (imm&0x1f))
        else:
            return "orr r%d, r%d, #0x%x" % (rd, rs, (imm>>5) << (imm&0x1f))
    elif (a,b) == (0x16,0):
        # See lsra
        return "lsrad r%d, r%d, #%d, #0x%x" % (rd, rs, imm&0x3f, imm>>6)
    elif (a,b) == (0x17,0):
        # See AND with mask above
        val = (0xffffffffffffffff ^ ((0x3ff ^ (imm>>6)) << (imm&0x3f))) & 0xffffffffffffffff
        return "andd r%d, r%d, #0x%x" % (rd, rs, val)
    elif (a,b) == (0x18,0):
        # OR with shifted imm
        if rs == 0:
            return "mov r%d, #0x%x" % (rd, (imm>>6) << (imm&0x3f))
        else:
            return "orrd r%d, r%d, #0x%x" % (rd, rs, (imm>>6) << (imm&0x3f))
    elif b == 0 and a < len(opc_i) and opc_i[a] is not None:
        # Register-immediate instructions
        if a == 1:
            lastadd = (rd, imm)
        if a == 1 and rs == 0:
            return "mov r%d, #0x%x" % (rd, imm)
        elif opc_i[a][:2] == "ls":
            return "%s r%d, r%d, #%d" % (opc_i[a], rd, rs, imm)
        else:
            return "%s r%d, r%d, #0x%x" % (opc_i[a], rd, rs, imm)
    elif b == 1 and a in (0x1, 0x2, 0x11, 0x12):
        # Register-immediate instructions (sign-extended arg)
        imm = s16(imm)
        if a == 1 and rs == 0:
            return "mov r%d, #0x%x" % (rd, s16(imm))
        elif imm < 0:
            return "%s r%d, r%d, #-0x%x" % (opc_i[a], rd, rs, -imm)
        else:
            return "%s r%d, r%d, #0x%x" % (opc_i[a], rd, rs, imm)
    elif b == 1 and a in (0x9, 0xa, 0xb):
        # Register-immediate logical instructions (sign-extended arg)
        imm = s16(imm)
        return "%s r%d, r%d, #0x%x" % (opc_i[a], rd, rs, s16(imm) & 0xffffffff)
    elif b == 1 and a in (0x19, 0x1a, 0x1b):
        # Register-immediate 64-bit logical instructions (sign-extended arg)
        imm = s16(imm)
        return "%s r%d, r%d, #0x%x" % (opc_i[a], rd, rs, s16(imm) & 0xffffffffffffffff)
    elif (a,b,rs,rd) == (0x20, 0,0,0):
        # Branch
        addlabel(imm)
        return "b %s  " % (loc(imm))
    elif (a,b,rd,imm) == (0x21, 0,0,0):
        # Branch register
        if lastadd is not None and lastadd[0] == rs:
            labels[lastadd[1]] = "_jmptab_0x%x" % lastadd[1]
        return "b r%d" % (rs)
    elif (a,b,rs,rd,imm) == (0x22, 0,0,0,0):
        # Branch jumptable
        return "btab\n"
    elif (a,b,rs,rd) == (0x23, 0,0,0):
        # Branch and link (call)
        addlabel(imm)
        return "bl %s  " % (loc(imm))
    elif (a,b,rs,rd,imm) == (0x24, 0,0,0,0):
        # Return
        return "ret\n"
    elif (a,b,rd) == (0x25, 0,0):
        # Compare and Branch if Zero
        addlabel(s16(imm)+off)
        return "cbz r%d, %s" % (rs, loc(s16(imm)+off))
    elif (a,b,rd) == (0x26, 0,0):
        # Compare and Branch if Nonzero
        addlabel(s16(imm)+off)
        return "cbnz r%d, %s" % (rs, loc(s16(imm)+off))
    elif a == 0x25:
        addlabel(s16(imm)+off)
        return "cbz? r%d, %s" % (rs, loc(s16(imm)+off))
    elif a == 0x26:
        addlabel(s16(imm)+off)
        return "cbnz? r%d, %s" % (rs, loc(s16(imm)+off))
    elif (a,rs) == (0x30,0):
        # Load immediate (other half may be 0000 or ffff)
        if b == 0:
            return "mov r%d, #0x%x" % (rd, imm)
        elif b == 1:
            return "mov r%d, #0x%x" % (rd, imm | 0xffff0000)
        elif b == 2:
            return "mov r%d, #0x%x" % (rd, imm<<16)
        elif b == 3:
            return "mov r%d, #0x%x" % (rd, (imm<<16) | 0xffff)
    elif 0x31 <= a <= 0x35:
        # Load/Store (word, double)
        # stm = store multiple (ctr register = num times) for streaming data
        op = ["ldw", "ldd", "stw", "std", "stm"][a - 0x31]
        if op[:2] == "st":
            return "%s r%d, %s[r%d, #0x%x]" % (op, rs, tgt, rd, imm)
        else:
            return "%s r%d, %s[r%d, #0x%x]" % (op, rd, tgt, rs, imm)
    elif a == 0x36:
        # Store immediate
        return "stw #0x%x, %s[r%d, #0x%x]" % (rs, tgt, rd, imm)
    elif (a,b,rs,imm) == (0x37, 2, 0, 0):
        # Move from counter
        return "mov r%d, ctr" % rd
    elif (a,b,rd,imm) == (0x37, 3, 0, 0):
        # Move to counter
        return "mov ctr, r%d" % rs
    elif (a,b,rd,imm) == (0x37, 1, 0, 0):
        # Pop stack
        return "push r%d" % rs
    elif (a,b,rs,imm) == (0x37, 0, 0, 0):
        # Pop stack
        return "pop r%d" % rd

    return "  dw 0x%x  #rs=%d rd=%d a=0x%x b=0x%x, imm=0x%x" % (inst, rs, rd, a, b, imm)

def print_hex(data):
    dl = len(data)
    for i in range(0, int(ceil(dl / 16))):
        for j in range(0, min(4, int((dl - i * 16)/4))):
            v = data[i * 16 + j * 4 + 0]
            v += data[i * 16 + j * 4 + 1] << 8
            v += data[i * 16 + j * 4 + 2] << 16
            v += data[i * 16 + j * 4 + 3] << 24
            opc = v << shift & 0xff
            #if opc in pkt3s:
            #    print(pkt3s[opc])
            #else:
            #    print("UNK")
            print(f"{v:08x}", end='')
        print('')
jtab = set()

with open(sys.argv[1], "rb") as f:
    odata = f.read();
    zstd_compressed = True
    for (i, b) in enumerate(reversed([0xfd, 0x2f, 0xb5, 0x28])):
        if odata[i] != b:
            zstd_compressed = False
            break

    if zstd_compressed:
        dctx = zstd.ZstdDecompressor()
        odata = dctx.decompress(odata)
    data = odata[0x40200:0x40357]
    dl = len(data)
    print(";-----------jmptab----------------")
    for i in range(0, dl//4*4, 4):
        v = read_word(data[i:])
        addr = (v & 0xffff)
        opcode = v >> 20 & 0xff
        pktname = f"PKT_0x{opcode:x}"
        if (opcode) in pkt3s:
            pktname = pkt3s[opcode]
        labels[addr] = pktname
        jtab.add(addr)
        print("; {0} = {1:x}".format(pktname, addr*4))
    print(";---------------------------------")
    data = odata[0x100+64*4:0x7a80]
    dl = len(data)
    last_command_end = 0

    for i in range(0, dl, 4):
        dis(i//4, read_word(data[i:]))
    lbc = 0
    lpref = "start"
    for i in range(0, dl, 4):
        if i//4 in jtab:
            lbc = 0
            lpref = labels[i//4]
        if i//4 in labels and labels[i//4] ==  True:
            labels[i//4] = f"{lpref}_{lbc}"
            lbc += 1
        if i < dl:
            dis(i//4, read_word(data[i:]))

    for i in range(0, dl, 4):
        if i//4 in labels:
            lab = labels[i//4]
            print(f"{lab}:")
        iw = read_word(data[i:])
        print(f"{i:04x}    {iw:08x}    ", end='')
        print(dis(i//4, iw))
