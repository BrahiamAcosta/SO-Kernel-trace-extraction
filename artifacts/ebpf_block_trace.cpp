/*
 * ebpf_block_trace.cpp – versión con diagnóstico mejorado
 * Usa múltiples tracepoints y añade debug exhaustivo
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
    // También a stderr para debug
    if (level <= LOG_WARNING) {
        std::cerr << msg << std::endl;
    }
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
// eBPF PROGRAM - Usando block_rq_complete que es más confiable
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

// Contador para debug
BPF_ARRAY(event_count, u64, 1);

// Intentar capturar desde block_rq_complete (más universal)
TRACEPOINT_PROBE(block, block_rq_complete) {
    int key = 0;
    u64 *count = event_count.lookup(&key);
    if (count) {
        (*count)++;
    }
    
    struct info_t info = {};
    
    // Estos campos son estándar en block_rq_complete
    info.sector = args->sector;
    info.bytes  = args->nr_sector * 512;
    info.ts     = bpf_ktime_get_ns();
    info.rw = 0;
    
    // Intentar leer rwbs de forma segura
    char rwbs_buf[8] = {};
    bpf_probe_read_kernel(&rwbs_buf, sizeof(rwbs_buf), (void*)args->rwbs);
    
    // Detectar escritura
    if (rwbs_buf[0] == 'W' || rwbs_buf[0] == 'w') {
        info.rw = 1;
    }
    
    // Solo enviar si hay datos válidos
    if (info.bytes > 0) {
        events.perf_submit(args, &info, sizeof(info));
    }
    
    return 0;
}

// También intentar con block_rq_issue como backup
TRACEPOINT_PROBE(block, block_rq_issue) {
    int key = 0;
    u64 *count = event_count.lookup(&key);
    if (count) {
        (*count)++;
    }
    
    struct info_t info = {};
    info.sector = args->sector;
    info.bytes  = args->nr_sector * 512;
    info.ts     = bpf_ktime_get_ns();
    info.rw = 0;
    
    char rwbs_buf[8] = {};
    bpf_probe_read_kernel(&rwbs_buf, sizeof(rwbs_buf), (void*)args->rwbs);
    
    if (rwbs_buf[0] == 'W' || rwbs_buf[0] == 'w') {
        info.rw = 1;
    }
    
    if (info.bytes > 0) {
        events.perf_submit(args, &info, sizeof(info));
    }
    
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
    uint64_t total_events_received;

    static void event_callback(void* cookie, void* data, int data_size) {
        if (!cookie) return;
        if (data_size < (int)sizeof(BlockEvent)) return;
        EBPFBlockTrace* self = static_cast<EBPFBlockTrace*>(cookie);
        BlockEvent ev;
        memcpy(&ev, data, sizeof(ev));
        self->process_event(ev);
    }

    void process_event(const BlockEvent& e) {
        total_events_received++;
        
        // Log primeros eventos para debug
        if (total_events_received <= 5) {
            log_msg("Event #" + std::to_string(total_events_received) + 
                   ": sector=" + std::to_string(e.sector) + 
                   " bytes=" + std::to_string(e.bytes) + 
                   " rw=" + std::to_string(e.rw), LOG_INFO);
        }
        
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
            << "] (reqs=" << stats.reqs << ", bytes=" << stats.bytes_acc << ")";
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

    bool write_readahead(int val) {
        std::string path = "/sys/block/sda/queue/read_ahead_kb";
        
        log_msg("Writing read_ahead_kb=" + std::to_string(val) + " to " + path, LOG_INFO);
        
        std::ofstream wf(path);
        if (!wf.is_open()) {
            log_msg("Failed writing sysfs: " + path + " - " + strerror(errno), LOG_WARNING);
            return false;
        }
        wf << val << std::endl;
        wf.close();
        
        return true;
    }

    void check_kernel_events() {
        // Leer contador de eventos del kernel
        auto table = bpf->get_array_table<uint64_t>("event_count");
        auto val = table.get_value(0);
        log_msg("Kernel event counter: " + std::to_string(val), LOG_INFO);
        
        if (val == 0) {
            log_msg("WARNING: No events detected in kernel. Tracepoint may not be active!", LOG_ERR);
        } else if (total_events_received == 0) {
            log_msg("WARNING: Events detected in kernel (" + std::to_string(val) + 
                   ") but not reaching userspace!", LOG_ERR);
        }
    }

public:
    EBPFBlockTrace(const std::string& dev, int winms, const std::string& sock)
        : device(dev), window_ms(winms), sock_path(sock), bpf(nullptr), 
          running(false), total_events_received(0) {}

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

            auto r2 = bpf->open_perf_buffer("events", event_callback, nullptr, this, 128);
            if (r2.code() != 0) {
                log_msg(std::string("perf buffer error: ") + r2.msg(), LOG_ERR);
                return false;
            }

            log_msg("eBPF initialized successfully (capturing all block devices)", LOG_INFO);
            log_msg("Attached to tracepoints: block:block_rq_complete and block:block_rq_issue", LOG_INFO);
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
        log_msg("Collector started (monitoring device: " + device + ")", LOG_INFO);
        double win_s = (double)window_ms / 1000.0;
        int window_count = 0;

        while (running) {
            auto window_start = std::chrono::steady_clock::now();
            auto window_end = window_start + std::chrono::milliseconds(window_ms);
            stats.reset();
            
            uint64_t events_at_start = total_events_received;
            
            // Poll más agresivamente
            while (std::chrono::steady_clock::now() < window_end && running) {
                bpf->poll_perf_buffer("events", 50);  // timeout reducido a 50ms
            }
            
            window_count++;
            uint64_t events_in_window = total_events_received - events_at_start;

            // Diagnóstico cada ventana
            log_msg("=== Window #" + std::to_string(window_count) + " ===", LOG_INFO);
            log_msg("Events in window: " + std::to_string(events_in_window), LOG_INFO);
            log_msg("Total events so far: " + std::to_string(total_events_received), LOG_INFO);
            
            // Verificar contador del kernel cada 5 ventanas
            if (window_count % 5 == 0) {
                check_kernel_events();
            }

            if (stats.reqs == 0) {
                log_msg("WARNING: No I/O requests captured in this window", LOG_WARNING);
                // Continuar sin enviar al daemon
                continue;
            }

            log_msg("Captured " + std::to_string(stats.reqs) + 
                   " requests, " + std::to_string(stats.bytes_acc) + " bytes", LOG_INFO);

            float feat[5];
            calculate_features(win_s, feat);

            int pred = send_to_daemon(feat);
            if (pred >= 0 && pred < 3) {
                int ra = READAHEAD_MAP[pred];
                if (write_readahead(ra)) {
                    log_msg(std::string("Prediction successful: class=") + CLASS_NAMES[pred] + 
                            " read_ahead_kb=" + std::to_string(ra), LOG_INFO);
                } else {
                    log_msg("Failed to write read_ahead_kb", LOG_WARNING);
                }
            } else {
                log_msg(std::string("No prediction or invalid class returned (pred=") + 
                       std::to_string(pred) + ")", LOG_WARNING);
            }
        }
        
        log_msg("Collector stopped. Total events received: " + 
               std::to_string(total_events_received), LOG_INFO);
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
        {"help", no_argument, 0, 'h'},
        {0,0,0,0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "d:w:s:h", long_opts, nullptr)) != -1) {
        if (opt == 'd') device = optarg;
        else if (opt == 'w') window_ms = atoi(optarg);
        else if (opt == 's') sock = optarg;
        else if (opt == 'h') {
            std::cout << "Usage: " << argv[0] << " [options]\n"
                      << "  -d, --device <dev>   Block device (default: sda2)\n"
                      << "  -w, --window <ms>    Window size in ms (default: 2500)\n"
                      << "  -s, --sock <path>    Socket path (default: /tmp/ml_predictor.sock)\n"
                      << "  -h, --help           Show this help\n";
            return 0;
        }
    }

    if (geteuid() != 0) {
        log_msg("Must run as root", LOG_ERR);
        std::cerr << "ERROR: Must run as root\n";
        return 1;
    }

    log_msg("Starting ebpf-blocktrace with device=" + device + 
            " window_ms=" + std::to_string(window_ms) + 
            " sock=" + sock, LOG_INFO);

    EBPFBlockTrace collector(device, window_ms, sock);
    g_ptr = &collector;

    signal(SIGINT, handler);
    signal(SIGTERM, handler);

    if (!collector.init()) {
        log_msg("Initialization failed", LOG_ERR);
        std::cerr << "ERROR: Initialization failed. Check syslog for details.\n";
        closelog();
        return 1;
    }

    // Mensaje inicial
    log_msg("eBPF collector is running. Generate I/O to see events...", LOG_INFO);
    log_msg("Test with: dd if=/dev/sda2 of=/dev/null bs=1M count=100", LOG_INFO);

    collector.run();
    closelog();
    return 0;
}
