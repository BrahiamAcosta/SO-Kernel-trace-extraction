sudo tee /usr/local/bin/ebpf_block_trace.py > /dev/null <<'PY'
#!/usr/bin/env python3
# ebpf_block_trace.py
# Recolecta stats via eBPF (tracepoints) y las manda al daemon /tmp/ml_predictor.sock
# Requiere: root, bcc

from bcc import BPF
from time import sleep, time
import socket, struct, os, sys, argparse

parser = argparse.ArgumentParser(description="eBPF -> ML bridge")
parser.add_argument("--device", default="nvme0n1", help="block device basename (ej: nvme0n1)")
parser.add_argument("--window_ms", type=int, default=2500, help="window size in ms (default 2500ms)")
parser.add_argument("--sock", default="/tmp/ml_predictor.sock", help="path to ml predictor unix socket")
args = parser.parse_args()

DEV = args.device
WINDOW_MS = args.window_ms
SOCK_PATH = args.sock

bpf_text = r"""
#include <uapi/linux/ptrace.h>
#include <linux/blkdev.h>
struct info_t {
    u64 sector;
    u32 bytes;
    u64 ts; // ns
    u32 rw; // 0 read, 1 write
};
BPF_PERF_OUTPUT(events);

TRACEPOINT_PROBE(block, block_rq_issue) {
    struct info_t info = {};
    struct request *req = (struct request *)args->rq;
    // some kernels pass sector in args->sector, others in req; try args first:
    info.sector = args->sector;
    info.bytes = args->nr_sector * 512;
    info.ts = bpf_ktime_get_ns();
    info.rw = (args->cmd_flags & REQ_OP_MASK) == REQ_OP_WRITE;
    events.perf_submit(args, &info, sizeof(info));
    return 0;
}
"""
# compile
b = BPF(text=bpf_text)

# perf event handler: aggregate windows in Python
# state
from collections import deque
sectors = deque()
bytes_acc = 0
reqs = 0
lat_total_ns = 0
# we'll approximate latency by time between issue and ... we also can track completes if needed
# For simplicity here: we use issue-only stats to compute avg distance, jump ratio, bw (bytes / window( s)), iops
last_sector = None
jumps = 0

def cb_event(cpu, data, size):
    global sectors, bytes_acc, reqs, last_sector, jumps
    sec, bts, ts, rw = struct.unpack("Q I Q I", data[:24])
    # push
    sectors.append(sec)
    bytes_acc += bts
    reqs += 1
    if last_sector is None:
        last_sector = sec
    else:
        d = sec - last_sector
        if d < 0: d = -d
        if d * 512 > 1000000: # >1MB jump
            jumps += 1
        last_sector = sec

b["events"].open_perf_buffer(cb_event)

print("ebpf bridge started (device=%s) → socket=%s; window=%dms" % (DEV, SOCK_PATH, WINDOW_MS))

# main loop
try:
    while True:
        start = time()
        # drain events for WINDOW_MS
        timeout = WINDOW_MS / 1000.0
        endt = start + timeout
        while time() < endt:
            b.perf_buffer_poll(timeout=100)
        # compute features
        if reqs == 0:
            avg_dist_sectors = 0.0
            jump_ratio = 0.0
            bw_kbps = 0.0
            iops_mean = 0.0
            lat_mean_ns = 0.0
        else:
            # average distance in sectors:
            # approximate by avg difference between consecutive sectors in deque:
            if len(sectors) <= 1:
                avg_dist_sectors = 0.0
            else:
                prev = None
                totald = 0
                cnt = 0
                for s in sectors:
                    if prev is not None:
                        d = s - prev
                        if d < 0: d = -d
                        totald += d
                        cnt += 1
                    prev = s
                avg_dist_sectors = (totald / cnt) if cnt>0 else 0.0
            jump_ratio = float(jumps) / float(reqs) if reqs>0 else 0.0
            # bw in KB/s
            bw_kbps = (bytes_acc / 1024.0) / (timeout)
            iops_mean = float(reqs) / (timeout)
            lat_mean_ns = 0.0  # not computed in this simple version (requires matching completes). Could be added.
        # convert avg_distance sectors -> bytes
        avg_dist_bytes = avg_dist_sectors * 512.0
        
        # Calculate average I/O size in bytes: (bandwidth in bytes/s) / IOPS
        # If IOPS is 0 or very small, use a fallback
        if iops_mean > 0.001:
            avg_io_size_bytes = (bw_kbps * 1024.0) / iops_mean
        else:
            avg_io_size_bytes = 0.0
        
        # Calculate sequential ratio (inverse of jump ratio)
        seq_ratio = max(0.0, min(1.0, 1.0 - jump_ratio))
        
        # build features in order expected by the model:
        # [0] avg_sector_distance_bytes: Distancia promedio entre offsets (bytes)
        # [1] sector_jump_ratio: Variabilidad (jump ratio)
        # [2] avg_io_size_bytes: Tamaño promedio de I/O (bytes)
        # [3] seq_ratio: Ratio secuencial (1 - jump_ratio)
        # [4] iops_mean: IOPS (operaciones por segundo)
        f0 = float(avg_dist_bytes)      # Feature 1: Distancia promedio
        f1 = float(jump_ratio)           # Feature 2: Variabilidad
        f2 = float(avg_io_size_bytes)    # Feature 3: Tamaño promedio I/O
        f3 = float(seq_ratio)            # Feature 4: Ratio secuencial
        f4 = float(iops_mean)            # Feature 5: IOPS
        # send to daemon via unix socket as 5 float32
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(SOCK_PATH)
            pkt = struct.pack('<5f', f0, f1, f2, f3, f4)
            sock.sendall(pkt)
            # read 4-byte int response
            resp = sock.recv(4)
            if len(resp) == 4:
                pred = struct.unpack('<i', resp)[0]
                # map to read_ahead_kb: adjust mapping as you prefer
                if pred == 0:
                    ra_kb = 256
                elif pred == 1:
                    ra_kb = 16
                else:
                    ra_kb = 64
                # write to sysfs
                dev = "%s" % ("{dev}".format(dev=DEV))
                path = "/sys/block/%s/queue/read_ahead_kb" % dev
                try:
                    with open(path, "w") as wf:
                        wf.write(str(ra_kb))
                    print("window: f=[dist=%.1f,jump=%.4f,size=%.1f,seq=%.4f,iops=%.1f] pred=%d(%s) set read_ahead_kb=%d" % 
                          (f0, f1, f2, f3, f4, pred, ["sequential","random","mixed"][pred], ra_kb))
                except Exception as e:
                    print("ERROR writing sysfs:", e)
            sock.close()
        except Exception as e:
            print("Socket error:", e)
        # reset counters
        sectors.clear()
        bytes_acc = 0
        reqs = 0
        jumps = 0
        last_sector = None
        # loop again
except KeyboardInterrupt:
    print("Stopping ebpf bridge")
    sys.exit(0)
PY
