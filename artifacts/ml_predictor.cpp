/*
 * ml_predictor.cpp
 * 
 * Daemon en C++ que carga el modelo TorchScript y ejecuta inferencia
 * Versión optimizada de alto rendimiento para producción
 * 
 * Compile:
 *   g++ -std=c++17 ml_predictor.cpp -o ml_predictor \
 *       -I$HOME/kml-project/libtorch/include \
 *       -I$HOME/kml-project/libtorch/include/torch/csrc/api/include \
 *       -L$HOME/kml-project/libtorch/lib \
 *       -ltorch -lc10 -ltorch_cpu -pthread -O3
 */

#include <torch/script.h>
#include <torch/torch.h>
#include <iostream>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <signal.h>
#include <cstring>
#include <vector>
#include <chrono>

// ============================================================================
// CONFIGURACIÓN
// ============================================================================

#define SOCKET_PATH "/tmp/ml_predictor.sock"
#define MODEL_PATH_DEFAULT "./model_ts.pt"
#define MAX_CONNECTIONS 10

// Parámetros de normalización (scaler)
static const float FEATURE_MEANS[5] = {
    5507101717.797395f,
    0.7057386400720898f,
    36776956.87843705f,
    0.2942613602238343f,
    1.0f
};

static const float FEATURE_STDS[5] = {
    5067766125.424761f,
    0.40276684902312826f,
    23396734.483704068f,
    0.40276684857585415f,
    1.0f
};

// Mapeo de clases
static const char* CLASS_NAMES[3] = {
    "sequential",
    "random",
    "mixed"
};

// ============================================================================
// CLASE PREDICTOR
// ============================================================================

class MLPredictor {
private:
    torch::jit::script::Module model;
    uint64_t prediction_count;
    
    // Normalizar features usando parámetros del scaler
    void normalize_features(const float* raw, float* normalized) {
        for (int i = 0; i < 5; i++) {
            if (FEATURE_STDS[i] > 0.0001f) {
                normalized[i] = (raw[i] - FEATURE_MEANS[i]) / FEATURE_STDS[i];
            } else {
                normalized[i] = 0.0f;
            }
        }
    }
    
public:
    MLPredictor(const std::string& model_path) : prediction_count(0) {
        std::cout << "Cargando modelo desde: " << model_path << std::endl;
        
        try {
            model = torch::jit::load(model_path);
            model.eval();  // Modo evaluación (desactiva dropout, etc.)
            
            std::cout << "✓ Modelo cargado correctamente" << std::endl;
        } catch (const c10::Error& e) {
            std::cerr << "❌ Error cargando modelo: " << e.what() << std::endl;
            throw;
        }
    }
    
    int predict(const float* raw_features) {
        auto start = std::chrono::high_resolution_clock::now();
        
        // Normalizar features
        float normalized[5];
        normalize_features(raw_features, normalized);
        
        // Crear tensor de entrada
        std::vector<torch::jit::IValue> inputs;
        auto options = torch::TensorOptions().dtype(torch::kFloat32);
        torch::Tensor input_tensor = torch::from_blob(
            normalized, 
            {1, 5},  // batch_size=1, features=5
            options
        ).clone();  // Clone para evitar problemas de memoria
        
        inputs.push_back(input_tensor);
        
        // Inferencia
        torch::Tensor output;
        {
            torch::NoGradGuard no_grad;  // Desactivar cálculo de gradientes
            output = model.forward(inputs).toTensor();
        }
        
        // Obtener clase predicha (argmax)
        int predicted_class = output.argmax(1).item<int>();
        
        prediction_count++;
        
        // Medir tiempo
        auto end = std::chrono::high_resolution_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
        
        // Log cada 100 predicciones
        if (prediction_count % 100 == 0) {
            std::cout << "[" << prediction_count << "] "
                      << "Predicción: " << CLASS_NAMES[predicted_class]
                      << " | Tiempo: " << duration.count() << " µs"
                      << " | Features: dist=" << raw_features[0]
                      << ", jump=" << raw_features[1]
                      << ", size=" << raw_features[2]
                      << std::endl;
        }
        
        return predicted_class;
    }
    
    uint64_t get_prediction_count() const {
        return prediction_count;
    }
};

// ============================================================================
// DAEMON
// ============================================================================

class PredictorDaemon {
private:
    MLPredictor* predictor;
    int server_fd;
    bool running;
    
    static PredictorDaemon* instance;
    
    static void signal_handler(int signum) {
        std::cout << "\n✓ Recibida señal " << signum << ". Cerrando daemon..." << std::endl;
        if (instance) {
            instance->shutdown();
        }
    }
    
public:
    PredictorDaemon(const std::string& model_path) : server_fd(-1), running(true) {
        predictor = new MLPredictor(model_path);
        instance = this;
        
        // Manejar señales
        signal(SIGINT, signal_handler);
        signal(SIGTERM, signal_handler);
    }
    
    ~PredictorDaemon() {
        if (predictor) {
            delete predictor;
        }
        if (server_fd >= 0) {
            close(server_fd);
        }
        unlink(SOCKET_PATH);
    }
    
    void shutdown() {
        running = false;
    }
    
    bool start() {
        std::cout << "============================================================" << std::endl;
        std::cout << "ML Predictor Daemon - Iniciando (C++ Optimizado)" << std::endl;
        std::cout << "============================================================" << std::endl;
        
        // Crear socket Unix
        server_fd = socket(AF_UNIX, SOCK_STREAM, 0);
        if (server_fd < 0) {
            std::cerr << "❌ Error creando socket: " << strerror(errno) << std::endl;
            return false;
        }
        
        // Eliminar socket previo
        unlink(SOCKET_PATH);
        
        // Configurar dirección
        struct sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path) - 1);
        
        // Bind
        if (bind(server_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            std::cerr << "❌ Error en bind: " << strerror(errno) << std::endl;
            return false;
        }
        
        // Listen
        if (listen(server_fd, MAX_CONNECTIONS) < 0) {
            std::cerr << "❌ Error en listen: " << strerror(errno) << std::endl;
            return false;
        }
        
        // Permisos
        chmod(SOCKET_PATH, 0666);
        
        std::cout << "✓ Escuchando en: " << SOCKET_PATH << std::endl;
        std::cout << "✓ Esperando peticiones del kernel..." << std::endl;
        std::cout << std::endl;
        
        // Loop principal
        while (running) {
            fd_set readfds;
            FD_ZERO(&readfds);
            FD_SET(server_fd, &readfds);
            
            struct timeval timeout;
            timeout.tv_sec = 1;
            timeout.tv_usec = 0;
            
            int activity = select(server_fd + 1, &readfds, NULL, NULL, &timeout);
            
            if (activity < 0 && errno != EINTR) {
                std::cerr << "❌ Error en select: " << strerror(errno) << std::endl;
                break;
            }
            
            if (activity > 0) {
                // Aceptar conexión
                int client_fd = accept(server_fd, NULL, NULL);
                if (client_fd < 0) {
                    if (errno != EINTR) {
                        std::cerr << "⚠️  Error en accept: " << strerror(errno) << std::endl;
                    }
                    continue;
                }
                
                // Leer features (5 floats = 20 bytes)
                float raw_features[5];
                ssize_t bytes_read = read(client_fd, raw_features, sizeof(raw_features));
                
                if (bytes_read != sizeof(raw_features)) {
                    std::cerr << "⚠️  Datos incompletos: " << bytes_read << " bytes" << std::endl;
                    close(client_fd);
                    continue;
                }
                
                // Predecir
                int predicted_class = predictor->predict(raw_features);
                
                // Enviar respuesta (1 int = 4 bytes)
                write(client_fd, &predicted_class, sizeof(predicted_class));
                
                close(client_fd);
            }
        }
        
        std::cout << "\n✓ Total de predicciones: " << predictor->get_prediction_count() << std::endl;
        std::cout << "✓ Daemon detenido" << std::endl;
        
        return true;
    }
};

PredictorDaemon* PredictorDaemon::instance = nullptr;

// ============================================================================
// MAIN
// ============================================================================

int main(int argc, char* argv[]) {
    std::string model_path = MODEL_PATH_DEFAULT;
    
    // Permitir especificar ruta del modelo
    if (argc > 1) {
        model_path = argv[1];
    }
    
    try {
        PredictorDaemon daemon(model_path);
        
        if (!daemon.start()) {
            return 1;
        }
        
    } catch (const std::exception& e) {
        std::cerr << "❌ Error fatal: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}
