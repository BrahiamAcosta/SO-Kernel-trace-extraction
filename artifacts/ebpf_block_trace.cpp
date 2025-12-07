/*
 * ebpf_block_trace.cpp
 * 
 * Recolector de estadísticas I/O usando eBPF (tracepoints) y comunicación
 * con el daemon ML predictor via Unix socket.
 * 
 * Migrado desde Python a C++ para unificar el stack tecnológico.
 * 
 * Requiere:
 *   - BCC (BPF Compiler Collection) con headers C++
 *   - Permisos root para usar eBPF
 * 
 * Compile:
 *   g++ -std=c++17 ebpf_block_trace.cpp -o ebpf_block_trace \
 *       -I/usr/include/bcc \
 *       -lbcc -lclang -lllvm
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

// BCC headers
// Nota: La ubicación exacta de los headers puede variar según la instalación
// En sistemas típicos: /usr/include/bcc/BPF.h
#include <BPF.h>
#include <bcc_common.h>

// ============================================================================
// CONFIGURACIÓN
// ============================================================================

#define DEFAULT_DEVICE "nvme0n1"
#define DEFAULT_WINDOW_MS 2500
#define DEFAULT_SOCK_PATH "/tmp/ml_predictor.sock"
#define JUMP_THRESHOLD_BYTES 1000000  // 1MB threshold for jumps

// Mapeo de predicciones a readahead_kb
static const int READAHEAD_MAP[3] = {256, 16, 64};  // sequential, random, mixed
static const char* CLASS_NAMES[3] = {"sequential", "random", "mixed"};

// ============================================================================
// ESTRUCTURAS DE DATOS
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
// CÓDIGO EBPF (igual que en Python)
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
    info.rw = (args->rwbs[0] == 'W');  // Write si rwbs empieza por W

    events.perf_submit(args, &info, sizeof(info));
    return 0;
}
)";


// ============================================================================
// CLASE EBPF COLLECTOR
// ============================================================================

class EBPFBlockTrace {
private:
    std::string device;
    int window_ms;
    std::string sock_path;
    ebpf::BPF* bpf;
    WindowStats stats;
    bool running;
    
    // Callback para eventos eBPF
    static void event_callback(void* cb_cookie, void* data, int data_size) {
    if (data_size != sizeof(BlockEvent)) return;

    BlockEvent* ev = reinterpret_cast<BlockEvent*>(data);
    EBPFBlockTrace* self = static_cast<EBPFBlockTrace*>(cb_cookie);
    self->process_event(*ev);
}

    
    void process_event(const BlockEvent& event) {
    stats.sectors.push_back(event.sector);
    stats.bytes_acc += event.bytes;
    stats.reqs++;

    if (stats.last_sector != 0) {
        int64_t d = llabs((long long)event.sector - (long long)stats.last_sector);
        if (d * 512 > JUMP_THRESHOLD_BYTES) {
            stats.jumps++;
        }
    }

    stats.last_sector = event.sector;
}

    
    // Calcular características desde estadísticas agregadas
    void calculate_features(double window_seconds, float* features) {
        if (stats.reqs == 0) {
            features[0] = 0.0f;  // avg_dist_bytes
            features[1] = 0.0f;  // jump_ratio
            features[2] = 0.0f;  // avg_io_size_bytes
            features[3] = 0.0f;  // seq_ratio
            features[4] = 0.0f;  // iops_mean
            return;
        }
        
        // Calcular distancia promedio entre sectores
        float avg_dist_sectors = 0.0f;
        if (stats.sectors.size() > 1) {
            uint64_t totald = 0;
            uint64_t cnt = 0;
            uint64_t prev = 0;
            bool first = true;
            
            for (uint64_t s : stats.sectors) {
                if (!first) {
                    int64_t d = static_cast<int64_t>(s) - static_cast<int64_t>(prev);
                    if (d < 0) d = -d;
                    totald += static_cast<uint64_t>(d);
                    cnt++;
                }
                prev = s;
                first = false;
            }
            avg_dist_sectors = (cnt > 0) ? (static_cast<float>(totald) / static_cast<float>(cnt)) : 0.0f;
        }
        
        // Convertir a bytes
        float avg_dist_bytes = avg_dist_sectors * 512.0f;
        
        // Jump ratio
        float jump_ratio = (stats.reqs > 0) ? (static_cast<float>(stats.jumps) / static_cast<float>(stats.reqs)) : 0.0f;
        
        // Bandwidth en KB/s
        float bw_kbps = (static_cast<float>(stats.bytes_acc) / 1024.0f) / static_cast<float>(window_seconds);
        
        // IOPS
        float iops_mean = static_cast<float>(stats.reqs) / static_cast<float>(window_seconds);
        
        // Tamaño promedio de I/O en bytes
        float avg_io_size_bytes = 0.0f;
        if (iops_mean > 0.001f) {
            avg_io_size_bytes = (bw_kbps * 1024.0f) / iops_mean;
        }
        
        // Ratio secuencial (1 - jump_ratio)
        float seq_ratio = 1.0f - jump_ratio;
        if (seq_ratio < 0.0f) seq_ratio = 0.0f;
        if (seq_ratio > 1.0f) seq_ratio = 1.0f;
        
        // Construir array de características (orden esperado por el modelo)
        features[0] = avg_dist_bytes;      // Feature 1: Distancia promedio
        features[1] = jump_ratio;         // Feature 2: Variabilidad
        features[2] = avg_io_size_bytes;  // Feature 3: Tamaño promedio I/O
        features[3] = seq_ratio;          // Feature 4: Ratio secuencial
        features[4] = iops_mean;          // Feature 5: IOPS
    }
    
    // Enviar características al daemon y recibir predicción
    int send_to_daemon(const float* features) {
        int sock_fd = socket(AF_UNIX, SOCK_STREAM, 0);
        if (sock_fd < 0) {
            std::cerr << "❌ Error creando socket: " << strerror(errno) << std::endl;
            return -1;
        }
        
        struct sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, sock_path.c_str(), sizeof(addr.sun_path) - 1);
        
        if (connect(sock_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            std::cerr << "⚠️  Error conectando al daemon: " << strerror(errno) << std::endl;
            close(sock_fd);
            return -1;
        }
        
        // Enviar 5 floats (20 bytes)
        ssize_t sent = send(sock_fd, features, 5 * sizeof(float), 0);
        if (sent != 5 * sizeof(float)) {
            std::cerr << "⚠️  Error enviando datos: " << strerror(errno) << std::endl;
            close(sock_fd);
            return -1;
        }
        
        // Recibir predicción (1 int = 4 bytes)
        int prediction = -1;
        ssize_t received = recv(sock_fd, &prediction, sizeof(int), 0);
        if (received != sizeof(int)) {
            std::cerr << "⚠️  Error recibiendo predicción: " << strerror(errno) << std::endl;
            close(sock_fd);
            return -1;
        }
        
        close(sock_fd);
        return prediction;
    }
    
    // Escribir readahead al sysfs
    bool write_readahead(const std::string& device, int readahead_kb) {
        std::string path = "/sys/block/" + device + "/queue/read_ahead_kb";
        std::ofstream file(path);
        if (!file.is_open()) {
            std::cerr << "⚠️  Error escribiendo sysfs: " << path << " - " << strerror(errno) << std::endl;
            return false;
        }
        file << readahead_kb;
        file.close();
        return true;
    }
    
public:
    EBPFBlockTrace(const std::string& dev, int win_ms, const std::string& sock)
        : device(dev), window_ms(win_ms), sock_path(sock), bpf(nullptr), running(false) {
    }
    
    ~EBPFBlockTrace() {
        if (bpf) {
            delete bpf;
        }
    }
    
    bool init() {
        try {
            bpf = new ebpf::BPF();
            auto init_res = bpf->init(BPF_PROGRAM);
            if (init_res.code() != 0) {
                std::cerr << "❌ Error inicializando BPF: " << init_res.msg() << std::endl;
                return false;
            }
            
            // Abrir perf buffer
            auto open_res = bpf->open_perf_buffer("events", event_callback, nullptr, this);
            if (open_res.code() != 0) {
                std::cerr << "❌ Error abriendo perf buffer: " << open_res.msg() << std::endl;
                return false;
            }
            
            std::cout << "✓ eBPF inicializado correctamente" << std::endl;
            return true;
        } catch (const std::exception& e) {
            std::cerr << "❌ Excepción inicializando BPF: " << e.what() << std::endl;
            return false;
        }
    }
    
    void run() {
        running = true;
        std::cout << "============================================================" << std::endl;
        std::cout << "eBPF Block Trace Collector (C++)" << std::endl;
        std::cout << "============================================================" << std::endl;
        std::cout << "Device: " << device << std::endl;
        std::cout << "Socket: " << sock_path << std::endl;
        std::cout << "Window: " << window_ms << " ms" << std::endl;
        std::cout << std::endl;
        
        double window_seconds = window_ms / 1000.0;
        
        while (running) {
            auto window_start = std::chrono::steady_clock::now();
            auto window_end = window_start + std::chrono::milliseconds(window_ms);
            
            stats.reset();
            
            // Poll eventos durante la ventana
            while (std::chrono::steady_clock::now() < window_end && running) {
                bpf->poll_perf_buffer("events", 100);  // timeout 100ms
            }
            
            // Calcular características
            float features[5];
            calculate_features(window_seconds, features);
            
            // Enviar al daemon
            int prediction = send_to_daemon(features);
            
            if (prediction >= 0 && prediction < 3) {
                // Mapear a readahead
                int readahead_kb = READAHEAD_MAP[prediction];
                
                // Escribir al sysfs
                if (write_readahead(device, readahead_kb)) {
                    std::cout << "window: f=[dist=" << features[0]
                              << ",jump=" << features[1]
                              << ",size=" << features[2]
                              << ",seq=" << features[3]
                              << ",iops=" << features[4]
                              << "] pred=" << prediction
                              << "(" << CLASS_NAMES[prediction] << ")"
                              << " set read_ahead_kb=" << readahead_kb
                              << std::endl;
                }
            } else if (prediction < 0) {
                std::cerr << "⚠️  No se pudo obtener predicción del daemon" << std::endl;
            }
        }
        
        std::cout << "\n✓ eBPF collector detenido" << std::endl;
    }
    
    void stop() {
        running = false;
    }
};

// ============================================================================
// HANDLER DE SEÑALES
// ============================================================================

static EBPFBlockTrace* g_collector = nullptr;

void signal_handler(int signum) {
    std::cout << "\n✓ Recibida señal " << signum << ". Deteniendo collector..." << std::endl;
    if (g_collector) {
        g_collector->stop();
    }
}

// ============================================================================
// MAIN
// ============================================================================

void print_usage(const char* prog_name) {
    std::cout << "Uso: " << prog_name << " [opciones]" << std::endl;
    std::cout << "Opciones:" << std::endl;
    std::cout << "  -d, --device DEVICE    Dispositivo block (default: " << DEFAULT_DEVICE << ")" << std::endl;
    std::cout << "  -w, --window MS         Tamaño de ventana en ms (default: " << DEFAULT_WINDOW_MS << ")" << std::endl;
    std::cout << "  -s, --sock PATH         Ruta al socket Unix (default: " << DEFAULT_SOCK_PATH << ")" << std::endl;
    std::cout << "  -h, --help              Mostrar esta ayuda" << std::endl;
}

int main(int argc, char* argv[]) {
    std::string device = DEFAULT_DEVICE;
    int window_ms = DEFAULT_WINDOW_MS;
    std::string sock_path = DEFAULT_SOCK_PATH;
    
    // Parsear argumentos
    static struct option long_options[] = {
        {"device", required_argument, 0, 'd'},
        {"window", required_argument, 0, 'w'},
        {"sock", required_argument, 0, 's'},
        {"help", no_argument, 0, 'h'},
        {0, 0, 0, 0}
    };
    
    int opt;
    int option_index = 0;
    while ((opt = getopt_long(argc, argv, "d:w:s:h", long_options, &option_index)) != -1) {
        switch (opt) {
            case 'd':
                device = optarg;
                break;
            case 'w':
                window_ms = std::atoi(optarg);
                if (window_ms <= 0) {
                    std::cerr << "❌ Error: window debe ser > 0" << std::endl;
                    return 1;
                }
                break;
            case 's':
                sock_path = optarg;
                break;
            case 'h':
                print_usage(argv[0]);
                return 0;
            default:
                print_usage(argv[0]);
                return 1;
        }
    }
    
    // Verificar permisos root
    if (geteuid() != 0) {
        std::cerr << "❌ Error: Este programa requiere permisos root para usar eBPF" << std::endl;
        std::cerr << "   Ejecuta con: sudo " << argv[0] << std::endl;
        return 1;
    }
    
    // Crear collector
    EBPFBlockTrace collector(device, window_ms, sock_path);
    g_collector = &collector;
    
    // Registrar handlers de señales
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    // Inicializar
    if (!collector.init()) {
        std::cerr << "❌ Error inicializando eBPF collector" << std::endl;
        return 1;
    }
    
    // Ejecutar
    collector.run();
    
    return 0;
}

