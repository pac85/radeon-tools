import sys

pkt3s = {}

with open("../f32/pkt3.txt") as f:
    for line in f:
        toks = line.split(' ')
        [pkt_name, opcode] = [toks[0], toks[-1]]
        opcode = int(opcode, 0)
        pkt3s[opcode] = pkt_name

def pkt3_opcode(pkt):
    return (pkt >> 8) & 0xff

def pkt3_count(pkt):
    return (pkt >> 16) & 0x3fff

def pkt_type(dword):
    return (dword >> 30) & 0x3

dword = int(sys.argv[1], 0)
if pkt_type(dword) == 3:
    opcode = pkt3_opcode(dword)
    pktname = f"PKT_0x{opcode:x}"
    if (opcode) in pkt3s:
        pktname = pkt3s[opcode]
    print("PKT3({}, {})".format(pktname, pkt3_count(dword)))
else:
    print("{:x}".format(dword))
