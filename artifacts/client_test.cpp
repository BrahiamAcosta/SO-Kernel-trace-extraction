#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <iostream>
#include <cstring>

#define SOCKET_PATH "/tmp/ml_predictor.sock"

int main() {
    int sock = socket(AF_UNIX, SOCK_STREAM, 0);

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path)-1);

    if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("connect");
        return 1;
    }

    // Features de prueba
    float features[5] = {
        4096.0f,   // dist bytes
        0.0f,      // jump_ratio (total secuencial)
        4096.0f,   // size
        1.0f,      // seq_ratio
        200.0f     // iops
    };

    write(sock, features, sizeof(features));

    int predicted;
    read(sock, &predicted, sizeof(predicted));

    std::cout << "Predicción recibida: " << predicted << std::endl;

    close(sock);
    return 0;
}
