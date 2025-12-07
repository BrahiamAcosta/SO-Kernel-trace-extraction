/*
 * ebpf_block_trace.cpp – versión para systemd (logging en syslog)
 */

#include <iostream>
#include <vector>
#include <deque>
#include <chrono>
#include <thread>
#include <cstring>
#include <cstdlib>
#include <csignal>
#include <fstream>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <getopt.h>
#include <syslog.h>

// BCC headers
#include <BPF.h>
#include <bcc_common.h>

// ============================================================================
// CONFIG
// ============================================================================

#define DEFAULT_DEVICE "nvme0n1"
#define DEFAULT_WINDOW_MS 2500
#define DEFAULT_SOCK_PATH "/tmp/ml_predictor.sock"
#define JUMP_THRESHOLD_BYTES 1000000

static const int READAHEAD_MAP[3] = {256, 16, 64};
static const char* CLASS_NAMES[3] = {"sequential", "random", "mixed"};

// ============================================================================
// Logging para systemd
// ============================================================================

void log_msg(const std::string& msg, int level = LOG_INFO) {
    syslog(level, "%s", msg.c_str());
}

// ============================================================================
// DATA STRUCTURES
// ============================================================================

struct BlockEvent {
    uint64_t sector;
    uint32_t bytes;
    uint64_t ts;
    uint32_t rw;
} __attribute__((packed));

struct WindowStats {
    std::deque<uint64_t> sectors;
    uint64_t bytes_acc;
    uint64_t reqs;
    uint64_t jumps;
    uint64_t last_sector;

    WindowStats() : bytes_acc(0), reqs(0), jumps(0), last_sector(0) {}

    void reset() {
        sectors.clear();
        bytes_acc = 0;
        reqs = 0;
        jumps = 0;
        last_sector = 0;
    }
};

// ============================================================================
// eBPF PROGRAM
// ============================================================================

static const char* BPF_PROGRAM = R"(
#include <uapi/linux/ptrace.h>
#include <linux/blkdev.h>

struct info_t {
    u64 sector;
    u32 bytes;
    u64 ts;
    u32 rw;
} __attribute__((packed));

BPF_PERF_OUTPUT(events);

TRACEPOINT_PROBE(block, block_rq_issue) {
    struct info_t info = {};
    struct request *req = (struct request *)args->rq;

    info.sector = req->sector;
    info.bytes = args->nr_sector * 512;
    info.ts = bpf_ktime_get_ns();
    info.rw = (args->rwbs[0] == 'W');

    events.perf_submit(args, &info, sizeof(info));
    return 0;
}
)";

// ============================================================================
// EBPF COLLECTOR CLASS
// ============================================================================

class EBPFBlockTrace {
private:
    std::string device;
    int window_ms;
    std::string sock_path;
    ebpf::BPF* bpf;
    WindowStats stats;
    bool running;

    static void event_callback(void* cookie, void* data, int data_size) {
        if (data_size != sizeof(BlockEvent)) return;
        EBPFBlockTrace* self = static_cast<EBPFBlockTrace*>(cookie);
        BlockEvent* ev = reinterpret_cast<BlockEvent*>(data);
        self->process_event(*ev);
    }

    void process_event(const BlockEvent& e) {
        stats.sectors.push_back(e.sector);
        stats.bytes_acc += e.bytes;
        stats.reqs++;

        if (stats.last_sector != 0) {
            int64_t d = llabs((long long)e.sector - (long long)stats.last_sector);
            if (d * 512 > JUMP_THRESHOLD_BYTES) stats.jumps++;
        }

        stats.last_sector = e.sector;
    }

    void calculate_features(double window_s, float* f) {
        if (stats.reqs == 0) {
            memset(f, 0, sizeof(float) * 5);
            return;
        }

        float avg_dist_sectors = 0;
        if (stats.sectors.size() > 1) {
            uint64_t total = 0;
            uint64_t cnt = 0;
            uint64_t prev = 0;
            bool first = true;

            for (uint64_t s : stats.sectors) {
                if (!first) {
                    int64_t d = s - prev;
                    if (d < 0) d = -d;
                    total += d;
                    cnt++;
                }
                prev = s;
                first = false;
            }
            avg_dist_sectors = (cnt > 0) ? (float)total / cnt : 0;
        }

        float avg_dist_bytes = avg_dist_sectors * 512.0f;
        float jump_ratio = (float)stats.jumps / (float)stats.reqs;
        float bw_kbps = (stats.bytes_acc / 1024.0f) / window_s;
        float iops = stats.reqs / window_s;

        float avg_io_bytes = (iops > 0.001f)
                                 ? (bw_kbps * 1024.0f) / iops
                                 : 0.0f;

        float seq_ratio = 1.0f - jump_ratio;
        if (seq_ratio < 0) seq_ratio = 0;
        if (seq_ratio > 1) seq_ratio = 1;

        f[0] = avg_dist_bytes;
        f[1] = jump_ratio;
        f[2] = avg_io_bytes;
        f[3] = seq_ratio;
        f[4] = iops;
    }

    int send_to_daemon(const float* f) {
        int sock = socket(AF_UNIX, SOCK_STREAM, 0);
        if (sock < 0) {
            log_msg("socket() failed: " + std::string(strerror(errno)), LOG_ERR);
            return -1;
        }

        struct sockaddr_un addr {};
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, sock_path.c_str(), sizeof(addr.sun_path) - 1);

        if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            log_msg("connect() failed: " + std::string(strerror(errno)), LOG_WARNING);
            close(sock);
            return -1;
        }

        if (send(sock, f, 5*sizeof(float), 0) != 5*sizeof(float)) {
            log_msg("send() error", LOG_WARNING);
            close(sock);
            return -1;
        }

        int pred = -1;
        if (recv(sock, &pred, sizeof(int), 0) != sizeof(int)) {
            log_msg("recv() error", LOG_WARNING);
            close(sock);
            return -1;
        }

        close(sock);
        return pred;
    }

    bool write_readahead(const std::string& dev, int val) {
        std::string path = "/sys/block/" + dev + "/queue/read_ahead_kb";
        std::ofstream f(path);
        if (!f.is_open()) {
            log_msg("sysfs write failed: " + path, LOG_WARNING);
            return false;
        }
        f << val;
        return true;
    }

public:
    EBPFBlockTrace(std::string dev, int winms, std::string sock)
        : device(dev), window_ms(winms), sock_path(sock), bpf(nullptr), running(false) {}

    ~EBPFBlockTrace() {
        if (bpf) delete bpf;
    }

    bool init() {
        try {
            bpf = new ebpf::BPF();
            auto r1 = bpf->init(BPF_PROGRAM);
            if (r1.code() != 0) {
                log_msg("BPF init error: " + r1.msg(), LOG_ERR);
                return false;
            }

            auto r2 = bpf->open_perf_buffer("events", event_callback, nullptr, this);
            if (r2.code() != 0) {
                log_msg("perf buffer error: " + r2.msg(), LOG_ERR);
                return false;
            }

            log_msg("eBPF initialized");
            return true;
        } catch (...) {
            log_msg("Exception initializing BPF", LOG_ERR);
            return false;
        }
    }

    void run() {
        running = true;

        log_msg("Collector started on device " + device);

        double win_s = window_ms / 1000.0;

        while (running) {
            auto end = std::chrono::steady_clock::now() + std::chrono::milliseconds(window_ms);

            stats.reset();

            while (std::chrono::steady_clock::now() < end && running) {
                bpf->poll_perf_buffer("events", 100);
            }

            float feat[5];
            calculate_features(win_s, feat);

            int pred = send_to_daemon(feat);
            if (pred >= 0 && pred < 3) {
                int ra = READAHEAD_MAP[pred];
                write_readahead(device, ra);

                log_msg(
                    "pred=" + std::string(CLASS_NAMES[pred]) +
                    " read_ahead_kb=" + std::to_string(ra)
                );
            }
        }

        log_msg("Collector stopped.");
    }

    void stop() { running = false; }
};

// ============================================================================
// SIGNAL HANDLER
// ============================================================================
static EBPFBlockTrace* g_ptr = nullptr;

void handler(int s) {
    log_msg("Signal received, stopping...");
    if (g_ptr) g_ptr->stop();
}

// ============================================================================
// MAIN
// ============================================================================

int main(int argc, char* argv[]) {
    openlog("ebpf-blocktrace", LOG_PID | LOG_CONS, LOG_USER);

    std::string device = DEFAULT_DEVICE;
    int window_ms = DEFAULT_WINDOW_MS;
    std::string sock = DEFAULT_SOCK_PATH;

    static struct option long_opts[] = {
        {"device", required_argument, 0, 'd'},
        {"window", required_argument, 0, 'w'},
        {"sock", required_argument, 0, 's'},
        {0, 0, 0, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "d:w:s:", long_opts, nullptr)) != -1) {
        if (opt == 'd') device = optarg;
        else if (opt == 'w') window_ms = atoi(optarg);
        else if (opt == 's') sock = optarg;
    }

    if (geteuid() != 0) {
        log_msg("Must run as root", LOG_ERR);
        return 1;
    }

    EBPFBlockTrace col(device, window_ms, sock);
    g_ptr = &col;

    signal(SIGINT, handler);
    signal(SIGTERM, handler);

    if (!col.init()) {
        log_msg("Init failed", LOG_ERR);
        return 1;
    }

    col.run();
    closelog();
    return 0;
}
