#!/bin/bash
# ============================================================
# 🧰 Script de instalación y configuración de entorno KML
# Autores: Brahiam Acosta - Juan Andres Rivera
# Fecha: $(date)
# Descripción: Instala herramientas esenciales, verifica versiones
#              y prepara la estructura de directorios.
# ============================================================

set -e  # Detener ejecución si ocurre un error

echo "=============================================="
echo "🚀 Iniciando instalación de entorno KML..."
echo "=============================================="

# --- Actualizar lista de paquetes ---
echo "🔄 Actualizando lista de paquetes..."
sudo apt update -y

# --- Instalar herramientas básicas ---
echo "🧩 Instalando herramientas básicas..."
sudo apt install -y \
    build-essential \
    git \
    vim \
    htop \
    tree \
    curl \
    wget

# --- Instalar headers del kernel ---
echo "🧠 Instalando headers del kernel..."
sudo apt install -y linux-headers-$(uname -r)

# --- Instalar LTTng completo ---
echo "📡 Instalando LTTng y herramientas relacionadas..."
sudo apt install -y \
    lttng-tools \
    lttng-modules-dkms \
    liblttng-ust-dev \
    babeltrace \
    python3-babeltrace

# --- Instalar herramientas de benchmarking ---
echo "📈 Instalando herramientas de benchmarking..."
sudo apt install -y \
    fio \
    sysbench \
    iotop \
    sysstat

# --- Instalar Python y librerías ---
echo "🐍 Instalando Python y utilidades..."
sudo apt install -y \
    python3-pip \
    python3-venv

# --- Instalar herramientas de desarrollo ---
echo "🛠️ Instalando herramientas de desarrollo..."
sudo apt install -y \
    cmake \
    pkg-config \
    libssl-dev

echo ""
echo "✅ Instalación de paquetes completada."
echo "----------------------------------------------"

# --- Verificaciones ---
echo "🔍 Verificando instalaciones..."

echo -n "LTTng versión: "
lttng version | head -n 1 || echo "❌ No instalado"

echo -n "FIO versión: "
fio --version || echo "❌ No instalado"

echo -n "Kernel headers: "
if [ -d /lib/modules/$(uname -r)/build ]; then
    echo "✅ Encontrado"
else
    echo "❌ No encontrado"
fi

echo -n "Python versión: "
python3 --version || echo "❌ No instalado"

# --- Crear estructura de directorios ---
echo ""
echo "📁 Creando estructura de trabajo en ~/kml-project..."
mkdir -p ~/kml-project/{traces,scripts,models,benchmarks,results}

cd ~/kml-project
echo "📂 Estructura creada:"
tree -L 1 || ls -d */

echo ""
echo "🎉 Instalación y configuración completadas con éxito."
echo "Tu entorno está listo en: ~/kml-project"
echo "=============================================="
