/*
 * ebpf_block_trace.cpp – versión para systemd - (logging en syslog)
 *
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
#include <sstream>
#include <iomanip>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <getopt.h>
#include <syslog.h>

// Si tu instalación de BCC requiere otro include, cámbialo (ej: <bcc/BPF.h>)
#include <BPF.h>
#include <bcc_common.h>

// ============================================================================
// CONFIG
// ============================================================================

#define DEFAULT_DEVICE "sda2"
#define DEFAULT_WINDOW_MS 2500
#define DEFAULT_SOCK_PATH "/tmp/ml_predictor.sock"
#define JUMP_THRESHOLD_BYTES 1000000

static const int READAHEAD_MAP[3] = {256, 16, 64};
static const char* CLASS_NAMES[3] = {"sequential", "random", "mixed"};

// ============================================================================
// Logging para systemd/journal
// ============================================================================

static void log_msg(const std::string& msg, int level = LOG_INFO) {
    syslog(level, "%s", msg.c_str());
}

// ============================================================================
// DATA STRUCTURES (usuario-side)
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
// eBPF PROGRAM (usa campos del tracepoint; NO usa struct request)
// ============================================================================

static const char* BPF_PROGRAM = R"(
#include <uapi/linux/ptrace.h>
#include <linux/blkdev.h>
#include <linux/trace_events.h>

/*
 * info_t: datos que entregaremos al userspace via perf buffer.
 */
struct info_t {
    u64 sector;
    u32 bytes;
    u64 ts;
    u32 rw;
} __attribute__((packed));

BPF_PERF_OUTPUT(events);

/*
 * block:block_rq_issue tracepoint layout puede variar entre kernels,
 * pero campos como sector, nr_sector y rwbs están disponibles en la mayoría
 * de versiones modernas. Aquí usamos args->sector, args->nr_sector y args->rwbs.
 */
TRACEPOINT_PROBE(block, block_rq_issue) {
    struct info_t info = {};
    // usa directamente fields del tracepoint args
    info.sector = args->sector;
    info.bytes  = args->nr_sector * 512;
    info.ts     = bpf_ktime_get_ns();

    // rwbs es típicamente una small char array con 'R' / 'W' en la primera posición.
    // Si no existe en una versión de kernel, rw quedará 0 (read) por defecto.
    info.rw = 0;
    // protect read of rwbs: algunos kernels siempre tienen 'rwbs' en el tracepoint
    // comprobamos usando try/catch semántico de C no existe; asumimos presencia.
    // Si tu kernel no tiene rwbs, esto devuelve 0 y lo considerará lectura.
    if (args->rwbs[0] == 'W')
        info.rw = 1;

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
        if (!cookie) return;
        if (data_size < (int)sizeof(BlockEvent)) return;
        EBPFBlockTrace* self = static_cast<EBPFBlockTrace*>(cookie);
        BlockEvent ev;
        // copiar de raw buffer (bcc ya deserializa según struct info_t)
        memcpy(&ev, data, sizeof(ev));
        self->process_event(ev);
    }

    void process_event(const BlockEvent& e) {
        stats.sectors.push_back(e.sector);
        stats.bytes_acc += e.bytes;
        stats.reqs++;

        if (stats.last_sector != 0) {
            long long diff = (long long)e.sector - (long long)stats.last_sector;
            if (diff < 0) diff = -diff;
            if ((unsigned long long)diff * 512 > (unsigned long long)JUMP_THRESHOLD_BYTES)
                stats.jumps++;
        }

        stats.last_sector = e.sector;
    }

    void calculate_features(double window_s, float* f) {
        if (stats.reqs == 0) {
            for (int i=0;i<5;i++) f[i]=0.0f;
            return;
        }

        // avg distance between consecutive sectors (in sectors)
        double avg_sectors = 0.0;
        if (stats.sectors.size() > 1) {
            unsigned long long totald = 0;
            unsigned long long cnt = 0;
            uint64_t prev = 0;
            bool first = true;
            for (uint64_t s : stats.sectors) {
                if (!first) {
                    long long d = (long long)s - (long long)prev;
                    if (d < 0) d = -d;
                    totald += (unsigned long long)d;
                    cnt++;
                }
                prev = s;
                first = false;
            }
            if (cnt) avg_sectors = (double)totald / (double)cnt;
        }

        float avg_bytes = (float)(avg_sectors * 512.0);
        float jump_ratio = (stats.reqs>0) ? ((float)stats.jumps / (float)stats.reqs) : 0.0f;
        float bw_kbps = ((float)stats.bytes_acc / 1024.0f) / (float)window_s;
        float iops = (float)stats.reqs / (float)window_s;
        float avg_io_bytes = (iops > 0.001f) ? ((bw_kbps * 1024.0f) / iops) : 0.0f;
        float seq_ratio = 1.0f - jump_ratio;
        if (seq_ratio < 0.0f) seq_ratio = 0.0f;
        if (seq_ratio > 1.0f) seq_ratio = 1.0f;

        f[0] = avg_bytes;
        f[1] = jump_ratio;
        f[2] = avg_io_bytes;
        f[3] = seq_ratio;
        f[4] = iops;
    }

    std::string format_features(const float* f) {
        std::ostringstream oss;
        oss << std::fixed << std::setprecision(4);
        oss << "Features=["
            << "avg_distance_bytes=" << f[0] << ", "
            << "jump_ratio=" << f[1] << ", "
            << "avg_io_bytes=" << f[2] << ", "
            << "seq_ratio=" << f[3] << ", "
            << "iops=" << f[4]
            << "]";
        return oss.str();
    }

    int send_to_daemon(const float* f) {
        std::string feat_str = format_features(f);
        log_msg("Sending to daemon: " + feat_str, LOG_INFO);

        int sock = socket(AF_UNIX, SOCK_STREAM, 0);
        if (sock < 0) {
            log_msg(std::string("socket() failed: ") + strerror(errno), LOG_ERR);
            return -1;
        }

        struct sockaddr_un addr;
        memset(&addr,0,sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, sock_path.c_str(), sizeof(addr.sun_path)-1);

        if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            log_msg(std::string("connect() failed: ") + strerror(errno), LOG_WARNING);
            close(sock);
            return -1;
        }

        ssize_t want = 5 * sizeof(float);
        ssize_t s = send(sock, f, want, 0);
        if (s != want) {
            log_msg("send() failed or partial send", LOG_WARNING);
            close(sock);
            return -1;
        }

        int pred = -1;
        ssize_t r = recv(sock, &pred, sizeof(pred), 0);
        if (r != (ssize_t)sizeof(pred)) {
            log_msg("recv() failed", LOG_WARNING);
            close(sock);
            return -1;
        }

        close(sock);
        return pred;
    }

    bool write_readahead(const std::string& dev, int val) {
        std::string path = std::string("/sys/block/sda/queue/read_ahead_kb");
        std::ofstream wf(path);
        if (!wf.is_open()) {
            log_msg("Failed writing sysfs: " + path, LOG_WARNING);
            return false;
        }
        wf << val << std::endl;
        return true;
    }

public:
    EBPFBlockTrace(const std::string& dev, int winms, const std::string& sock)
        : device(dev), window_ms(winms), sock_path(sock), bpf(nullptr), running(false) {}

    ~EBPFBlockTrace() {
        if (bpf) delete bpf;
    }

    bool init() {
        try {
            bpf = new ebpf::BPF();
            auto r1 = bpf->init(BPF_PROGRAM);
            if (r1.code() != 0) {
                log_msg(std::string("BPF init error: ") + r1.msg(), LOG_ERR);
                return false;
            }

            auto r2 = bpf->open_perf_buffer("events", event_callback, nullptr, this);
            if (r2.code() != 0) {
                log_msg(std::string("perf buffer error: ") + r2.msg(), LOG_ERR);
                return false;
            }

            log_msg("eBPF initialized", LOG_INFO);
            return true;
        } catch (const std::exception &e) {
            log_msg(std::string("Exception initializing BPF: ") + e.what(), LOG_ERR);
            return false;
        } catch (...) {
            log_msg("Unknown exception initializing BPF", LOG_ERR);
            return false;
        }
    }

    void run() {
        running = true;
        log_msg("Collector started on device " + device, LOG_INFO);
        double win_s = (double)window_ms / 1000.0;

        while (running) {
            auto window_end = std::chrono::steady_clock::now() + std::chrono::milliseconds(window_ms);
            stats.reset();
            while (std::chrono::steady_clock::now() < window_end && running) {
                // poll perf buffer; timeout 100 ms
                bpf->poll_perf_buffer("events", 100);
            }

            float feat[5];
            calculate_features(win_s, feat);

            int pred = send_to_daemon(feat);
            if (pred >= 0 && pred < 3) {
                int ra = READAHEAD_MAP[pred];
                if (write_readahead(device, ra)) {
                    log_msg(std::string("Prediction successful: class=") + CLASS_NAMES[pred] + 
                            " read_ahead_kb=" + std::to_string(ra), LOG_INFO);
                } else {
                    log_msg("failed to write read_ahead_kb", LOG_WARNING);
                }
            } else {
                log_msg(std::string("no prediction or invalid class returned (pred=") + std::to_string(pred) + ")", LOG_WARNING);
            }
        }
        log_msg("Collector stopped.", LOG_INFO);
    }

    void stop() { running = false; }
};

// ============================================================================
// SIGNAL HANDLER
// ============================================================================

static EBPFBlockTrace* g_ptr = nullptr;
static void handler(int s) {
    log_msg("Signal received, stopping...", LOG_INFO);
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
        {0,0,0,0}
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

    EBPFBlockTrace collector(device, window_ms, sock);
    g_ptr = &collector;

    signal(SIGINT, handler);
    signal(SIGTERM, handler);

    if (!collector.init()) {
        log_msg("Init failed", LOG_ERR);
        closelog();
        return 1;
    }

    collector.run();
    closelog();
    return 0;
}
